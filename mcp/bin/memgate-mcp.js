#!/usr/bin/env node
// memgate-mcp launcher: spawns the bundled Python MCP server (stdio passthrough).
'use strict';
const { spawn } = require('child_process');
const path = require('path');
const py = process.env.PYTHON || 'python3';
const child = spawn(py, [path.join(__dirname, '..', 'mcp_server.py')], { stdio: 'inherit' });
child.on('error', (err) => { console.error('memgate-mcp: failed to launch ' + py + ': ' + err.message); process.exit(1); });
child.on('exit', (code, signal) => { if (signal) process.exit(1); process.exit(code == null ? 0 : code); });
