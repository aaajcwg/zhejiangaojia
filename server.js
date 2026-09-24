#!/usr/bin/env node
/**
 * 浙江建材报价系统 - 可选静态托管（零依赖）
 * 用途：把本目录（含 zhejiang-building-material-quote.html + prices.json）托管起来，
 *       手机连同一局域网即可访问，打开即自动拉取 prices.json 实现“实时价”。
 * 用法：node server.js  然后访问 http://<本机局域网IP>:3000
 * 说明：本文件【不是必须】的。你也可以把这两个文件放到任意 Web 服务器 /
 *       NAS / k3s Ingress / GitHub Pages 等静态托管上，效果相同。
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = process.env.PORT || 3000;
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.ico': 'image/x-icon'
};

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/zhejiang-building-material-quote.html';
  const fp = path.join(ROOT, path.normalize(p).replace(/^(\.\.[/\\])+/, ''));
  if (!fp.startsWith(ROOT)) { res.writeHead(403); return res.end('forbidden'); }
  fs.readFile(fp, (err, data) => {
    if (err) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(fp).toLowerCase()] || 'application/octet-stream' });
    res.end(data);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('浙江建材报价系统已托管：');
  console.log('  本机：  http://localhost:' + PORT);
  console.log('  手机：  http://<本机局域网IP>:' + PORT + '  （需与手机同一 WiFi/网络）');
});
