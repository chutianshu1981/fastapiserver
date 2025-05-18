# Project Guidelines

## Documentation Requirements

### 1. Code Comments
- **Clarity and Purpose**: All functions, classes, and complex logic blocks should have clear and concise comments explaining their purpose, parameters, return values, and any non-obvious behavior. Use type hinting for function signatures.
- **Docstrings**: Follow PEP 257 for docstring conventions. For example, use Google style docstrings.
  ```python
  def my_function(param1: int, param2: str) -> bool:
      """Does something interesting.

      Args:
          param1: The first parameter.
          param2: The second parameter.

      Returns:
          True if successful, False otherwise.
      """
      # ... logic ...
      return True
  ```
- **Inline Comments**: Use inline comments sparingly, only for parts of code that are not immediately obvious.
- **TODO/FIXME**: Use `TODO:` for planned enhancements and `FIXME:` for known issues that need addressing, optionally followed by your initials or a ticket number (e.g., `TODO(cline): Refactor this section`).

### 2. API Documentation
- **OpenAPI/Swagger**: For all Flask API endpoints, maintain an up-to-date OpenAPI (Swagger) specification. This should ideally be auto-generated (e.g., using libraries like `flasgger`) or meticulously manually maintained in `docs/api/openapi.yaml`.
- **Endpoint Descriptions**: Each endpoint documentation must clearly state its purpose, HTTP method, URL path, request parameters (path, query, header, cookie) with types and validation rules, expected request body structure (with media types like `application/json`), and all possible response codes with their corresponding response body structures and media types.
- **Examples**: Include example requests (e.g., cURL commands, JSON bodies) and responses for each endpoint.
- **Authentication/Authorization**: Clearly document any authentication or authorization mechanisms required for accessing endpoints.

### 3. README.md
- **Project Overview**: The main `README.md` in the `src/` directory should provide a comprehensive overview of the project:
    - Its purpose (RTSP stream server).
    - How it works at a high level (receives Android app push, allows live playback).
    - Key technologies used (Flask, Gstreamer).
- **Setup and Installation**: Detailed, step-by-step instructions for:
    - Cloning the repository.
    - Setting up the Python environment (e.g., using `pdm install`).
    - Installing Gstreamer and any required plugins.
    - Configuring environment variables (with a `.env.example` file).
- **Running the Application**:
    - How to start the Flask server (e.g., `pdm run start`).
    - How to run any Gstreamer-related standalone processes or scripts, if applicable.
    - Default ports and URLs (e.g., `http://localhost:8554/push`).
- **Key Features & Endpoints**:
    - List main features.
    - Briefly describe important API endpoints like `/push`, including expected input and output.
- **Directory Structure**: A brief explanation of the project's directory layout (e.g., `src/app`, `src/app/api`, `src/app/rtsp`).
- **Troubleshooting**: Common issues and their solutions (e.g., Gstreamer pipeline errors, port conflicts).
- **Contribution Guidelines**: (Optional, but good for team projects) How to contribute, coding standards, pull request process.

## Code Style & Patterns

### 1. Python (Flask)
- **PEP 8**: Strictly adhere to PEP 8 style guidelines.
- **Flask Blueprints**: Organize API endpoints and related logic into Flask Blueprints for better modularity (as seen in `src/app/api/`).
- **Configuration**: Centralize configuration in `src/app/core/config.py`. Use Pydantic for settings management, loading from environment variables. Provide a `.env.example` file.
- **Error Handling**:
    - Implement consistent error handling using Flask's error handlers (`@app.errorhandler`).
    - Define custom exception classes for application-specific errors (e.g., `RTSPStreamError`).
    - Return meaningful JSON error responses with appropriate HTTP status codes.
- **Logging**:
    - Utilize the logging module configured in `src/app/core/logger.py`.
    - Ensure logs are structured (e.g., JSON format) for easier parsing and analysis.
    - Log relevant contextual information (e.g., request ID, user ID if applicable).
    - Use appropriate log levels: `DEBUG` for detailed development info, `INFO` for operational messages, `WARNING` for potential issues, `ERROR` for errors that prevent normal operation, `CRITICAL` for severe errors.
- **Type Hinting**: Use Python type hints extensively for all function signatures and variables where appropriate (PEP 484). Run `mypy` for static type checking.

### 2. General Patterns
- **Separation of Concerns (SoC)**:
    - API layer (`src/app/api/routes.py`): Handles HTTP requests, validation, and responses.
    - Service layer (`src/app/services/video_service.py`): Contains business logic, orchestrates operations (e.g., interacting with `RtspServer`).
    - RTSP/Gstreamer layer (`src/app/rtsp/server.py`): Manages all Gstreamer-specific operations.
- **Dependency Management**: Use `pdm` and `pyproject.toml` for managing Python dependencies. Regularly update dependencies (`pdm update`) and audit for vulnerabilities (`pdm audit`).
- **Immutability**: Prefer immutable data structures where practical.
- **Avoid Global State**: Minimize the use of global variables. If necessary, manage them explicitly within application context or configuration objects.
- **Idempotency**: Design API endpoints (especially `PUT`, `DELETE`) to be idempotent where appropriate.
- **File Length**: Aim for single files to not exceed 300 lines of code. The absolute maximum should be 500 lines. Strive for well-structured, reasonably sized modules to enhance readability and maintainability.

## Testing Standards

### 1. Unit Tests
- **Coverage**: Aim for high unit test coverage (e.g., >80%) for all critical components, especially business logic (services), utility functions, and API request/response models.
- **Framework**: Use `pytest` as the testing framework.
- **Test Structure**:
    - Organize tests mirroring the project structure (e.g., `src/tests/api/test_routes.py`, `src/tests/rtsp/test_server.py`).
    - Test files should be named `test_*.py` or `*_test.py`.
    - Test methods should be named `test_*`.
- **Assertions**: Use clear and specific assertions provided by `pytest`.
- **Mocking**:
    - Use `pytest-mock` (which wraps `unittest.mock`) to isolate units under test from external dependencies (e.g., actual Gstreamer calls, network requests, database interactions).
    - Mock Gstreamer objects and their methods when testing logic that interacts with Gstreamer, rather than trying to run actual Gstreamer pipelines in unit tests.
- **Fixtures**: Utilize `pytest` fixtures for setting up and tearing down test preconditions (e.g., creating a test Flask client, mock RtspServer instances).

### 2. Integration Tests
- **Scope**: Test interactions between different components of the system.
    - Example: API endpoint receiving a request -> VideoService -> Mocked RtspServer.
    - Test that Flask routes correctly call service methods and handle their responses/exceptions.
- **Focus**: Verify data flow, communication paths, and contract adherence between components.
- **Gstreamer Integration (Limited)**:
    - Full Gstreamer pipeline integration tests can be complex and resource-intensive for CI.
    - Consider separate, manually-run tests or a dedicated testing environment for full end-to-end Gstreamer pipeline validation if necessary.
    - For automated integration tests, focus on the interaction points with the Gstreamer module, potentially using more sophisticated mocks or stubs for the Gstreamer parts.

### 3. Test Execution
- **CI/CD**: Integrate test execution (`pdm run test`) into the CI/CD pipeline (e.g., GitHub Actions, GitLab CI). Builds should fail if tests do not pass or coverage drops below a threshold.
- **Readability**: Tests should be readable and serve as documentation for the code they are testing.
- **Test Data**: Use realistic but controlled test data. Avoid dependencies on external systems or pre-existing data states.
