from __future__ import annotations

import os
import time
from snowl.envs import GuiEnv
from snowl.core import EnvSpec


import subprocess
import random
import string
from snowl.envs import GuiEnv
from snowl.core import EnvSpec

def random_container_name():
    return "osworld-test-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

def stop_osworld_container(container_id):
    print(f"[TEST] Stopping container {container_id}...")
    subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)

def test_gui_env_interaction():
    # 自动注入 BOOT 环境变量，优先使用 OSWORLD_DEFAULT_BOOT_URL
    from snowl.runtime.container_runtime import ContainerRuntime
    # 自动下载并挂载 qcow2 镜像
    runtime = ContainerRuntime(
        task_id="test",
        agent_id="test",
        variant_id="test",
        task_env_type="gui",
        task_metadata={"benchmark": "osworld"},
        sample={},
    )
    # 合并 DockerProvider 的默认环境变量
    docker_default_env = {"DISK_SIZE": "32G", "RAM_SIZE": "4G", "CPU_CORES": "4"}
    container_env, volumes, _, _ = runtime._resolve_osworld_boot_inputs()
    for k, v in docker_default_env.items():
        if k not in container_env:
            container_env[k] = v
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
    print("[TEST] Starting OSWorld docker container via GuiEnv...")
    start_info = env.start_container(env=container_env, volumes=volumes, cap_add=runtime._resolve_osworld_cap_add())
    if start_info.get("exit_code", 1) != 0 or not start_info.get("ready", False):
        print("[ERROR] Could not start OSWorld container.")
        return
    try:
        print("[TEST] Observing initial state...")
        obs = env.observe(include_accessibility=True, include_terminal=True)
        print("[TEST] Screenshot status:", obs.get("status_code"))
        print("[TEST] Accessibility status:", obs.get("accessibility_status_code"))
        print("[TEST] Terminal status:", obs.get("terminal_status_code"))

        print("[TEST] Starting recording...")
        rec_start = env.start_recording()
        print("[TEST] Recording started:", rec_start)
        print("[TEST] Executing MOVE_TO action...")
        move_evt = env.execute_action({"action_type": "MOVE_TO", "parameters": {"x": 100, "y": 100, "duration": 0.2}})
        print("[TEST] MOVE_TO result:", move_evt)

        print("[TEST] Saving screenshot...")
        screenshot_bytes = obs.get("screenshot", b"")
        if screenshot_bytes:
            screenshot_path = ".snowl/recordings/test_env_interaction_screenshot1.png"
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            print(f"[TEST] Screenshot saved: {screenshot_path} ({len(screenshot_bytes)} bytes)")
        else:
            print("[TEST] No screenshot data available.")
        print("[TEST] Executing CLICK action...")
        click_evt = env.execute_action({"action_type": "CLICK", "parameters": {"x": 100, "y": 100, "button": "left", "num_clicks": 1}})
        print("[TEST] CLICK result:", click_evt)
        print("[TEST] Saving screenshot...")
        screenshot_bytes = obs.get("screenshot", b"")
        if screenshot_bytes:
            screenshot_path = ".snowl/recordings/test_env_interaction_screenshot2.png"
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            print(f"[TEST] Screenshot saved: {screenshot_path} ({len(screenshot_bytes)} bytes)")
        else:
            print("[TEST] No screenshot data available.")
        print("[TEST] Executing TYPING action...")
        type_evt = env.execute_action({"action_type": "TYPING", "parameters": {"text": "hello world"}})
        print("[TEST] TYPING result:", type_evt)

        print("[TEST] Executing SCROLL action...")
        scroll_evt = env.execute_action({"action_type": "SCROLL", "parameters": {"dx": 0, "dy": -400}})
        print("[TEST] SCROLL result:", scroll_evt)

        print("[TEST] Executing HOTKEY action...")
        hotkey_evt = env.execute_action({"action_type": "HOTKEY", "parameters": {"keys": ["ctrl", "s"]}})
        print("[TEST] HOTKEY result:", hotkey_evt)

        print("[TEST] Saving screenshot...")
        screenshot_bytes = obs.get("screenshot", b"")
        if screenshot_bytes:
            screenshot_path = ".snowl/recordings/test_env_interaction_screenshot.png"
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            print(f"[TEST] Screenshot saved: {screenshot_path} ({len(screenshot_bytes)} bytes)")
        else:
            print("[TEST] No screenshot data available.")

        
        time.sleep(2)
        print("[TEST] Ending recording...")
        #rec_end = env.end_recording()
        #print("[TEST] Recording ended:", rec_end)
        #if rec_end.get("ok", False):
        rec_path = ".snowl/recordings/test_env_interaction.mp4"
        save_evt = env.save_recording(rec_path)
        print("[TEST] Recording saved:", save_evt)
        #env.close()
    finally:
        print("[TEST] Stopping container via GuiEnv...")
        #env.stop_container()

if __name__ == "__main__":
    test_gui_env_interaction()
