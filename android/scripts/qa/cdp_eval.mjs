// usage: node cdp_eval.mjs <forwarded port> <javascript expression>
const [port, expr] = process.argv.slice(2);
const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = list.find(t => t.type === 'page') || list[0];
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => { ws.onopen = r; });
ws.send(JSON.stringify({id: 1, method: 'Runtime.evaluate', params: {expression: expr, returnByValue: true}}));
const msg = await new Promise(r => { ws.onmessage = e => r(JSON.parse(e.data)); });
const res = msg.result.result;
console.log(JSON.stringify(res.value !== undefined ? res.value : res));
ws.close();
