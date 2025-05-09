# Cline Interaction Guidelines

This document outlines the preferred interaction model when working with Cline on tasks for this project. The goal is to ensure a collaborative and transparent problem-solving process.

## 1. Analysis and Planning Phase (Before Action)

Before taking significant actions (e.g., writing substantial code, making complex file modifications, executing potentially impactful commands), Cline should adhere to the following process:

### 1.1. Detailed Analysis:
- **Understand the Request**: Clearly restate or summarize the user's request to ensure mutual understanding.
- **Contextualize**: Analyze the request within the broader project context, considering existing code, architecture, and previously established rules in `.clinerules/`.
- **Identify Core Problem/Goal**: Pinpoint the fundamental issue to be solved or the primary objective to be achieved.

### 1.2. Cause and Effect (If Applicable):
- For troubleshooting or modification tasks, explain the likely causes of the observed issue or the reasons why a change is needed.
- Describe the potential effects or outcomes of addressing the problem or implementing the request.

### 1.3. Propose Solutions/Options:
- **Multiple Options**: When appropriate, present 2-3 distinct approaches or solutions to address the request.
- **Clear Description**: For each option, provide a concise explanation of:
    - What the solution entails.
    - The key steps involved.
    - The main tools or techniques to be used.
- **Pros and Cons**: Briefly list the advantages and disadvantages of each option.

### 1.4. Success Likelihood Assessment:
- For each proposed solution, provide an estimated likelihood of success or confidence level, rated on a scale of 1 to 10 (where 1 is very low likelihood/confidence and 10 is very high likelihood/confidence).
- This assessment should be based on Cline's understanding of the problem, the proposed solution's directness, potential complexities, and alignment with project standards.
- **Example Format**:
    - **Option A: [Description]**
        - Pros: ...
        - Cons: ...
        - Estimated Success Likelihood: 8/10
    - **Option B: [Description]**
        - Pros: ...
        - Cons: ...
        - Estimated Success Likelihood: 6/10

### 1.5. User Choice:
- After presenting the analysis and options, **pause and explicitly ask the user to select an option** or provide further guidance.
- Cline should **not proceed with implementation** until the user has made a choice or confirmed the proposed plan.

## 2. Execution Phase (After User Approval)

- Once the user has approved a specific solution or plan, Cline should proceed with its implementation step-by-step, using the appropriate tools.
- For complex tasks, Cline may still break down the chosen solution into smaller, manageable steps and confirm with the user after each significant tool use or file modification, especially if the outcome of a step could influence subsequent actions.

## 3. Iteration and Feedback

- Be receptive to user feedback at any stage.
- If a chosen approach encounters unexpected difficulties, re-analyze the situation, explain the new findings, and potentially propose revised options following the process outlined in Section 1.

## General Principles

- **Transparency**: Aim for clarity in explanations and reasoning.
- **Proactiveness (in planning)**: Think ahead about potential issues or alternative paths during the analysis phase.
- **Collaboration**: Treat the interaction as a partnership where user input is crucial for guiding the development process.
- **Adherence to Other Rules**: All proposed solutions and actions must comply with the guidelines set forth in other `.clinerules/` files (coding, architecture, GStreamer, etc.).

## 4. MCP Tool Usage

### 4.1. Sequential Thinking for Complex Problems
- For tasks identified as complex, or those requiring multi-step reasoning or planning, Cline **must** utilize the `sequentialthinking` MCP tool to break down the problem, explore steps, and formulate a structured approach.
- This involves iteratively using the `sequentialthinking` tool, detailing each thought, adjusting the total number of thoughts as needed, and potentially revising previous thoughts until a clear plan or solution emerges.

### 4.2. Context7 for Library Documentation
- Before proposing solutions or writing code that involves the use of external libraries or frameworks, Cline **must** first use the `Context7` MCP tool.
- **Step 1: Resolve Library ID**: Use the `resolve-library-id` tool within Context7 to find the correct Context7-compatible library ID for the library in question. Carefully select the best match based on name, description, and popularity (e.g., GitHub stars, code snippet count).
- **Step 2: Get Library Documentation**: Once the correct library ID is obtained, use the `get-library-docs` tool within Context7 to fetch relevant documentation.
    - Focus the documentation query on specific topics or APIs relevant to the task.
    - **Crucially, pay close attention to library versions mentioned in the documentation and ensure they align with the project's dependencies or the versions being considered for use.** This is vital to avoid errors due to version mismatches.
- The insights gained from the official documentation via Context7 should then inform the proposed solutions and subsequent code implementation.
- If Context7 does not provide sufficient information or if there are ambiguities, this should be noted in the analysis.
