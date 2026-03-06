from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from snowl.benchmarks.osworld.container import OSWorldContainerLauncher
from snowl.core import EnvSpec
from snowl.envs import GuiEnv


def test_gui_env_interaction() -> None:
    if str(os.getenv("SNOWL_RUN_DOCKER_INTEGRATION", "0")).lower() not in {"1", "true", "yes"}:
        pytest.skip("Set SNOWL_RUN_DOCKER_INTEGRATION=1 to run Docker integration tests.")

    launcher = OSWorldContainerLauncher(repo_root=Path.cwd(), emit=None)
    container_env, volumes, _, _ = launcher._resolve_boot_inputs()
    ports, _ = launcher._resolve_ports()
    cap_add = launcher._resolve_cap_add()

    env = GuiEnv(
        env_spec=EnvSpec(
            env_type="gui",
            provided_ops=(
                "gui.action",
                "gui.click",
                "gui.type",
                "gui.key",
                "gui.scroll",
                "gui.observe",
                "gui.wait",
                "gui.terminate",
            ),
        ),
        config={
            "ready_timeout_sec": float(os.getenv("SNOWL_OSWORLD_READY_TIMEOUT", "240")),
        },
    )

    start_info = env.start_container(
        image=os.getenv("SNOWL_OSWORLD_IMAGE", "happysixd/osworld-docker"),
        env=container_env,
        ports=ports,
        volumes=volumes,
        cap_add=cap_add,
    )
    if int(start_info.get("exit_code", 1)) != 0 or not bool(start_info.get("ready", False)):
        logs = env.container_logs(tail=200)
        env.stop_container()
        raise AssertionError(
            "OSWorld container did not become ready. "
            f"start={start_info!r}, logs={logs!r}"
        )

    try:
        obs = env.observe(include_accessibility=True, include_terminal=True)
        assert int(obs.get("status_code", 0)) == 200

        rec_start = env.start_recording()
        assert bool(rec_start.get("ok", False))

        move_evt = env.execute_action({"action_type": "MOVE_TO", "parameters": {"x": 100, "y": 100, "duration": 0.2}})
        assert int(move_evt.get("status_code", 0)) == 200

        click_evt = env.execute_action({"action_type": "CLICK", "parameters": {"x": 100, "y": 100, "button": "left", "num_clicks": 1}})
        assert int(click_evt.get("status_code", 0)) == 200

        type_evt = env.execute_action({"action_type": "TYPING", "parameters": {"text": "hello world"}})
        assert int(type_evt.get("status_code", 0)) == 200

        scroll_evt = env.execute_action({"action_type": "SCROLL", "parameters": {"dx": 0, "dy": -400}})
        assert int(scroll_evt.get("status_code", 0)) == 200

        hotkey_evt = env.execute_action({"action_type": "HOTKEY", "parameters": {"keys": ["ctrl", "s"]}})
        assert int(hotkey_evt.get("status_code", 0)) == 200

        time.sleep(2.0)

        save_evt = env.save_recording(".snowl/recordings/test_env_interaction.mp4")
        assert bool(save_evt.get("ok", False))
    finally:
        env.stop_container()
        env.close()
