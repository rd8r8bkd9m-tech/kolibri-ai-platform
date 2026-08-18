import http from "node:http";

const TARGET = "http://127.0.0.1:8002";
const PORT = 8082;

const server = http.createServer((req, res) => {
	const allow = {
		"access-control-allow-origin": req.headers.origin || "*",
		"access-control-allow-headers":
			req.headers["access-control-request-headers"] || "authorization,content-type",
		"access-control-allow-methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS",
		"access-control-max-age": "600",
	};
	if (req.method === "OPTIONS") {
		res.writeHead(204, allow);
		res.end();
		return;
	}
	const headers = { ...req.headers };
	delete headers.origin;
	delete headers.host;
	const proxyReq = http.request(new URL(req.url, TARGET), {
		method: req.method,
		headers,
	}, (proxyRes) => {
		res.writeHead(proxyRes.statusCode, { ...proxyRes.headers, ...allow });
		proxyRes.pipe(res);
	});
	proxyReq.on("error", () => {
		res.writeHead(502, allow);
		res.end("proxy error");
	});
	req.pipe(proxyReq);
});

server.listen(PORT, () => console.log("CORS proxy on", PORT, "->", TARGET));
