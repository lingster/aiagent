# AI Agent 

An MCP server to give your AI Agent access to a Linux shell, in a safe docker container. 

Are you a developer who has used Claude Code but have been ratching up a large API bill?
*21-Jun-2025 UPDATE* - So I only found out that you can now use Claude Code with a Pro or MAX subscription, so the above is no longer true! 

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

## MCP Server Options

This project now supports **two ways** to use the MCP server:

### Option 1: Local/stdio Mode (Original)
Claude Desktop connects directly to the MCP server via stdio transport.

**Claude config (`claude_desktop_config.json`):**
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

### Option 2: Remote MCP Server (NEW!)
Connect to the MCP server over HTTP using the Streamable HTTP transport with Server-Sent Events (SSE).

**✨ Features:**
- 🌐 **Remote access** - Connect from anywhere over HTTP/HTTPS
- 🔐 **API key authentication** - Secure your server
- 📊 **SSE streaming** - Real-time output from long-running commands
- 🔄 **Session management** - Stateful connections
- 🚀 **Multiple clients** - Multiple AI agents can connect simultaneously

#### Remote MCP Setup

1. **Configure environment variables** (see `.env.example`):
```bash
MCP_REMOTE_PORT=8888        # Port for remote MCP server
MCP_API_KEY=your-secret-key # Generate with: openssl rand -base64 32
MCP_PORT=8181               # Backend API port
```

2. **Start the backend** (if using Docker):
```bash
docker compose up -d app
```

3. **Start the remote MCP server**:

   **Option A - Standalone (recommended for development):**
   ```bash
   uv run mcp_remote_server.py
   ```

   **Option B - In Docker (for production):**
   Uncomment the `mcp-remote` service in `docker-compose.yml`, then:
   ```bash
   docker compose up -d mcp-remote
   ```

4. **Connect with Claude Desktop using Custom Connectors**:

   In Claude Desktop settings → Connectors → Add custom connector:
   - URL: `http://localhost:8888/mcp`
   - Authentication: Bearer token with your `MCP_API_KEY`

5. **Or connect with other MCP clients** (like the example with Linear):
```json
{
  "mcpServers": {
    "shelltools": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8888/mcp"],
      "env": {
        "MCP_API_KEY": "your-secret-key"
      }
    }
  }
}
```

#### Remote MCP API Endpoints

- `POST /mcp` - Main endpoint for JSON-RPC requests (returns JSON or SSE stream)
- `GET /mcp` - Server-initiated SSE stream (currently returns 405)
- `DELETE /mcp` - Terminate session
- `GET /health` - Health check endpoint

#### Security Features

- **API Key Authentication** - All requests require valid Bearer token
- **Origin Validation** - Prevents DNS rebinding attacks
- **Session Management** - Secure session IDs with timeout
- **Localhost Binding** - Server binds to 127.0.0.1 by default

#### Streaming Command Output

The remote MCP server streams output from long-running commands in real-time using Server-Sent Events:

```bash
# Client sends request to execute command
POST /mcp
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "execute_linux_shell_command",
    "arguments": {"cmd": "npm run build"}
  }
}

# Server responds with SSE stream:
event: stdout
data: {"content": "Building..."}

event: stdout
data: {"content": "✓ Build complete"}

event: message
data: {"jsonrpc": "2.0", "id": 1, "result": {...}}
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

## Customise to your workflow and coding languages
By default the docker container contains python (uv) and node (nvm) as pre-installed packages.
But you have complete freedom to adjust to your workflow.
You can also amend the docker-compose file an expose ports from docker back to host, ideal if you are building 
apps that need network access.

## Example prompts to try:

```
Using shelltools what's in the /data directory?
```
This should retun the contents of your mounted volume/directory. 

```
Using shelltools write a factorial script in python, then run this to calculate the factorial of 7 supplied as a command line arg
```

```
create a hello world web page and host it using node 
```

## BONUS: My Tips:
If you are using Claude Desktop as your MCP client, take advantage of the Projects feature and create a new project for each of your code project. Include documentation and other relevant attachments. Then customise your custom prompt for that project with your own personal coding conventions.

## Known Issues
Some times the llm may run a command in the shell which never returns for example `npm run dev`.
This would block future commands from being executed. In this case just restart the docker container with:
`docker compose up -d --force-recreate app`

## Contributing 
PRs and suggestions welcome.

Happy coding!
