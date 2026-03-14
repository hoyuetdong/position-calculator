{
  "name": "vcp-position-calculator",
  "script": "npm",
  "args": "start",
  "instances": 1,
  "autorestart": true,
  "watch": false,
  "max_memory_restart": "500M",
  "env": {
    "NODE_ENV": "production",
    "PORT": 3000,
    "FUTU_HOST": "127.0.0.1",
    "FUTU_PORT": "11111"
  },
  "error_file": "/var/log/pm2/vcp-calc-error.log",
  "out_file": "/var/log/pm2/vcp-calc-out.log",
  "log_date_format": "YYYY-MM-DD HH:mm:ss Z",
  "merge_logs": true
}