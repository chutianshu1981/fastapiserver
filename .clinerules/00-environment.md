# Development Environment Context

This document provides essential context about the development environment for this project. Cline should refer to this information to ensure its actions and commands are appropriate for the setup.

## 1. Operating System and Shell

-   **Host OS**: Windows 11
-   **Development Environment**: WSL2 (Windows Subsystem for Linux 2)
-   **Linux Distribution**: Ubuntu 24.x
-   **Default Shell in WSL2**: zsh (specifically, oh-my-zsh)
-   **Key Consideration**: All development activities, command-line operations, and file system interactions relevant to the project occur *within the WSL2 Ubuntu environment*.

## 2. IDE and AI Tools

-   **Integrated Development Environment (IDE)**: Visual Studio Code (VSCode)
-   **VSCode Usage**: VSCode is used by directly opening the project folder located within the WSL2 file system (e.g., `vscode .` from the project root in WSL2).
-   **AI Assistant Plugin**: Cline
-   **Large Language Model (LLM)**: Gemini 2.5 Pro (or latest available Gemini Pro model)
-   **LLM API Access**: Via Google AI API

## 3. Python Development Environment

-   **Python Version**: 3.12.3
-   **Package and Dependency Manager**: PDM
-   **Project Root Directory**: `/home/chutianshu/fastapiserver`
    -   Cline's current working directory is typically this root directory.
-   **Source Code Directory**: `/home/chutianshu/fastapiserver/src`
    -   All primary application source code resides here.
-   **Python Virtual Environment**:
    -   **Location**: `/home/chutianshu/fastapiserver/src/.venv`
    -   **Management**: Managed by PDM.
    -   **Activation**: While Cline might not directly "activate" it in the same way a user does, it's crucial to understand that Python commands (e.g., `python`, `pip`, `pdm run`) should execute within the context of this PDM-managed environment to use the correct interpreter and packages.

## 4. Key Instructions for Cline

-   **Command Execution**:
    -   All CLI commands should be formulated for execution within the WSL2 (Ubuntu 24) environment, from the project root directory (`/home/chutianshu/fastapiserver`).
    -   When running Python scripts or PDM commands, ensure they respect the project's PDM setup (e.g., use `pdm run <script>` or ensure the correct Python interpreter from `.venv` is implicitly or explicitly used).
-   **File Paths**:
    -   All file paths provided or generated should be Linux-style paths, relative to the WSL2 filesystem.
    -   Be mindful of the project root (`/home/chutianshu/fastapiserver`) and source directory (`/home/chutianshu/fastapiserver/src`) when referencing files.
-   **Dependency Management**:
    -   Any suggestions for adding, removing, or updating Python packages should be compatible with PDM (e.g., "use `pdm add <package>`" rather than "use `pip install <package>`").
-   **Tooling Awareness**:
    -   Recognize that tools like linters, formatters, and test runners are likely configured within `pyproject.toml` and managed by PDM.
-   **No Windows Paths**: Avoid generating or expecting Windows-style paths (e.g., `C:\Users\...`) for project files.
