"""Create a custom component template"""

import inspect
import json
import pathlib
import shutil
import subprocess
import textwrap
from typing import Optional

import typer
from typing_extensions import Annotated

import gradio
from gradio.cli.commands.display import LivePanelDisplay

package_json = {
    "name": "<component-name>",
    "version": "0.0.1",
    "description": "Custom Component",
    "type": "module",
    "main": "./index.svelte",
    "author": "",
    "license": "ISC",
    "private": True,
    "exports": {
        ".": "./index.svelte",
        "./package.json": "./package.json",
        "./interactive": "./interactive/index.ts",
        "./static": "./static/index.ts",
        "./example": "./example/index.ts",
    },
    "dependencies": {
        "@gradio/atoms": "workspace:^",
        "@gradio/statustracker": "workspace:^",
        "@gradio/utils": "workspace:^",
    },
}

app = typer.Typer()


def _create_frontend_dir(name: str, dir: pathlib.Path):
    dir.mkdir(exist_ok=True)
    (dir / f"{name}.svelte").write_text("")
    (dir / "index.ts").write_text(f'export {{ default }} from "./{name}.svelte";')


def _create_frontend(name: str, template: str, directory: pathlib.Path):
    package_json["name"] = name

    frontend = directory / "frontend"
    frontend.mkdir(exist_ok=True)

    if not template:
        for dirname in ["example", "interactive", "shared", "static"]:
            dir = frontend / dirname
            _create_frontend_dir(name, dir)
    else:
        p = pathlib.Path(inspect.getfile(gradio)).parent

        def ignore(s, names):
            ignored = []
            for n in names:
                if (
                    n.startswith("CHANGELOG")
                    or n.startswith("README.md")
                    or ".test." in n
                    or ".stories." in n
                ):
                    ignored.append(n)
            return ignored

        shutil.copytree(
            str(p / "_frontend_code" / template),
            frontend,
            dirs_exist_ok=True,
            ignore=ignore,
        )

    json.dump(package_json, open(str(frontend / "package.json"), "w"), indent=2)


def _create_backend(name: str, template: str, directory: pathlib.Path):
    backend = directory / "backend" / name.lower()
    backend.mkdir(exist_ok=True, parents=True)

    gitignore = pathlib.Path(__file__).parent / "files" / "gitignore"
    gitignore_contents = gitignore.read_text()
    gitignore_dest = directory / ".gitignore"
    gitignore_dest.write_text(gitignore_contents)

    pyproject = pathlib.Path(__file__).parent / "files" / "pyproject_.toml"
    pyproject_contents = pyproject.read_text()
    pyproject_dest = directory / "pyproject.toml"
    pyproject_dest.write_text(pyproject_contents.replace("<<name>>", name.lower()))

    demo_dir = directory / "demo"
    demo_dir.mkdir(exist_ok=True, parents=True)

    (demo_dir / "app.py").write_text(
        f"""
import gradio as gr
from {name.lower()} import {name}

with gr.Blocks() as demo:
    {name}()

demo.launch()
"""
    )
    (demo_dir / "__init__.py").touch()

    init = backend / "__init__.py"
    init.write_text(
        f"""
from .{name.lower()} import {name}

__all__ = ['{name}']
"""
    )

    if not template:
        backend = backend / f"{name.lower()}.py"
        backend.write_text(
            textwrap.dedent(
                f"""
            import gradio as gr
            
            class {name}(gr.components.Component):
                pass

            """
            )
        )
    else:
        p = pathlib.Path(inspect.getfile(gradio)).parent
        python_file = backend / f"{name.lower()}.py"

        shutil.copy(
            str(p / "components" / f"{template.lower()}.py"),
            str(python_file),
        )

        source_pyi_file = p / "components" / f"{template.lower()}.pyi"
        pyi_file = backend / f"{name.lower()}.pyi"
        if source_pyi_file.exists():
            shutil.copy(str(source_pyi_file), str(pyi_file))

        content = python_file.read_text()
        python_file.write_text(content.replace(f"class {template}", f"class {name}"))
        if pyi_file.exists():
            pyi_content = pyi_file.read_text()
            pyi_file.write_text(
                pyi_content.replace(f"class {template}", f"class {name}")
            )


@app.command("create", help="Create a new component.")
def _create(
    name: Annotated[
        str,
        typer.Argument(
            help="Name of the component. Preferably in camel case, i.e. MyTextBox."
        ),
    ],
    directory: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            help="Directory to create the component in. Default is None. If None, will be created in <component-name> directory in the current directory."
        ),
    ] = None,
    template: Annotated[
        str,
        typer.Option(
            help="Component to use as a template. Should use exact name of python class."
        ),
    ] = "",
    install: Annotated[
        bool,
        typer.Option(
            help="Whether to install the component in your current environment as a local install"
        ),
    ] = False,
):
    if not directory:
        directory = pathlib.Path(name.lower())

    directory.mkdir(exist_ok=True)

    with LivePanelDisplay() as live:
        live.update(
            f":building_construction:  Creating component [orange3]{name}[/] in directory [orange3]{directory}[/]",
            add_sleep=0.2,
        )
        if template:
            live.update(f":fax: Starting from template [orange3]{template}[/]")
        else:
            live.update(":page_facing_up: Creating a new component from scratch.")

        _create_frontend(name.lower(), template, directory=directory)
        live.update(":art: Created frontend code", add_sleep=0.2)

        _create_backend(name, template, directory)
        live.update(":snake: Created backend code", add_sleep=0.2)

        if install:
            cmds = ["pip", "install", "-e", f"{str(directory)}"]
            live.update(
                f":construction_worker: Installing... [grey37]({' '.join(cmds)})[/]"
            )
            pipe = subprocess.run(cmds, capture_output=True, text=True)
            if pipe.returncode != 0:
                live.update(":red_square: Installation [bold][red]failed[/][/]")
                live.update(pipe.stderr)
            else:
                live.update(":white_check_mark: Install succeeded!")


@app.command(
    "dev",
    help=("Launch the custom component demo in development mode. " "Must be in the "),
)
def dev(
    app: Annotated[
        pathlib.Path,
        typer.Argument(
            help="The path to the app. By default, looks for demo/app.py in the current directory."
        ),
    ] = pathlib.Path("demo")
    / "app.py",
    component_directory: Annotated[
        pathlib.Path,
        typer.Option(
            help="The directory with the custom component source code. By default, uses the current directory."
        ),
    ] = pathlib.Path("."),
):
    component_directory = component_directory.resolve()
    if not (component_directory / "pyproject.toml").exists():
        raise ValueError(
            f"Cannot find pyproject.toml file in {component_directory}. Make sure "
            f"{component_directory} parameter points to a valid python package."
        )

    with LivePanelDisplay() as live:
        live.update(f":recycle: [green]Launching[/] {app} in reload mode")
        proc = subprocess.Popen(
            ["gradio", str(app), "--watch-dirs", component_directory],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        while True:
            text = proc.stdout.readline()
            text = (
                text.decode("utf-8")
                .replace("Changes detected in:", "[orange3]Changed detected in:[/]")
                .replace("Watching:", "[orange3]Watching:[/]")
            )
            live.update(text)


@app.command(
    "build",
    help="Build the component for distribution. Must be called from the component directory.",
)
def build(
    path: Annotated[
        str, typer.Argument(help="The directory of the custom component.")
    ] = ".",
    build_frontend: Annotated[
        bool, typer.Option(help="Whether to build the frontend as well.")
    ] = True,
):
    name = pathlib.Path(path).resolve()
    if not (name / "pyproject.toml").exists():
        raise ValueError(f"Cannot find pyproject.toml file in {name}")

    with LivePanelDisplay() as live:
        live.update(
            f":package: Building package in [orange3]{str(name.name)}[/]", add_sleep=0.2
        )
        if build_frontend:
            live.update(":art: Building frontend")

        cmds = ["python", "-m", "build", str(name)]
        live.update(f":construction_worker: Building... [grey37]({' '.join(cmds)})[/]")
        pipe = subprocess.run(cmds, capture_output=True, text=True)
        if pipe.returncode != 0:
            live.update(":red_square: Build failed!")
            live.update(pipe.stderr)
        else:
            live.update(":white_check_mark: Build succeeded!")
            live.update(
                f":ferris_wheel: Wheel located in [orange3]{str(name / 'dist')}[/]"
            )


def main():
    app()