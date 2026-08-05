import tomllib
from pathlib import Path


def test_admin_web_assets_are_declared_as_package_data():
    project = tomllib.loads(Path("pyproject.toml").read_text())

    assert project["tool"]["setuptools"]["package-data"]["dzmm_bot"] == [
        "admin/static/*.js",
        "admin/templates/*.html",
    ]
