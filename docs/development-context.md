# VideoBox Development Context

## Folder Roles

- Development folder: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`
  - This is the source code and development workspace for building the VideoBox program.
  - Code, architecture notes, implementation docs, tests, and developer tooling belong here.

- Project folder: `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`
  - This is the operational project folder used after the program exists and is being used.
  - Generated outputs, working project data, runtime artifacts, and user-facing results belong here.

## Working Rule

- Do not mix development source files with operational project outputs.
- Treat the development folder as the product-building workspace.
- Treat the project folder as the production/usage workspace for assets and results created by the program.

## Current Decision

- The two folders above are intentionally separate and should stay separate unless an explicit architecture decision changes this later.
