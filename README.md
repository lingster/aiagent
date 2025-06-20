# AI Agent 

An MCP server to give your AI Agent access to a Linux shell, in a safe docker container. 

Are you a developer who has used Claude Code but have been ratching up a large API bill?
Then try this MCP server. This will give your Claude Desktop access to a linux shell
to write and build your code, create and run unit tests and run your code from the 
safety of being inside a docker container! 

Alternatively add to MCP server to any other MCP Client and give your choosen LLM full shell access.

## Quick Installation Steps

### Pre-requistes 
Ensure you have:
- docker / docker compose installed
- uv + python installed: 

### Install steps
- Update the .env file to point to the directory where you have your code checked out. 
- Run: `docker compose up -d --force-recreate app` 
- Add this mcp server to your `claude_config.json` (see below)
- (Re)Start claude desktop 
- Create a new project and add the CUSTOM_INSTRUCTIONS.md as your custom system prompt.

### Additional installation notes for your operating system:
#### Linux
Add the following to the ~/.config/Claude/claude_desktop_config.json(in linux):

Amend Dockerfile with these settings:
```
ARG USER_UID=1000
ARG USER_GID=1000
```

### Windows
After installing claude, ensure that you have enabled developer mode:
```
settings (top left hand corner) help->enable developer mode
```

The Claude Config file is located in: `%APPDATA%\Claude\claude_desktop_config.json`

You may need to create this config file if it does not already exist.

Amend Dockerfile with these settings:
```
ARG USER_UID=1001
ARG USER_GID=1001
```


### Macos
In macos this is located in: `~/Library/Application Support/Claude`

Amend Dockerfile with these settings:
```
ARG USER_UID=502
ARG USER_GID=20
```

## Claude config changes
```json
{
    "shelltools": {  
      "command": "uv",                           
      "args": [                           
        "--directory",                           
        "<PATH_TO>//aiagent/",                           
        "run",                           
        "mcp_server.py"                           
      ]                           
    }
}
```

## How does this work? The details
This repo contains a Dockerfile which can be started up and provides a REST API interface to allow shell
commands to run in a safe docker environment. 

By default the data directory is mapped to /data in the docker container. All code edits etc will take place
in this location. 

By default the data directory is mapped to /data in the docker container. All code edits etc will take place

`mcp_server.py` implements shell commands and these commands are sent via REST API to the docker container.
Presently commands can be run as sync or async. If async they will be run as background tasks and a process id will
be returned. 

If we want to run directly on the local machine, this can be configured, set `USE_DOCKER=False` as your env var.

## Knonwn Issues
Some times the llm may run a command in the shell which never returns for example `npm run dev`.
This would block future commands from being executed. In this case just restart the docker container with:
`docker compose up -d --force-recreate app`

## Contributing 
PRs and suggestions welcome.

Happy coding!
