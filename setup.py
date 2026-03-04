from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).resolve().parent


setup(
    name="snowl",
    version="0.1.0",
    description="Snowl: a general agent evaluation framework.",
    long_description=(ROOT / "DESIGN.md").read_text(encoding="utf-8") if (ROOT / "DESIGN.md").exists() else "",
    long_description_content_type="text/markdown",
    packages=find_packages(include=["snowl", "snowl.*"]),
    include_package_data=True,
    package_data={
        "snowl.ui": ["panel_configs/*.yml", "panel_configs/*.yaml", "panel_configs/README.md"],
    },
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.25",
        "PyYAML>=6.0",
        "requests>=2.31",
        "rich>=13.7",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "snowl=snowl.cli:main",
        ]
    },
)
