// TLS in front of `next start`.
//
// `next dev --experimental-https` exists; `next start` has no equivalent, and
// the microphone is only offered on a secure origin. So production builds get
// served through this: it terminates TLS with the same self-signed
// certificate the launcher already generates and forwards to Next on
// localhost.
//
// Why bother, when dev mode can do HTTPS on its own: dev mode recompiles per
// route and there is a window where the page arrives before its stylesheet.
// On a laptop that is a flicker. On a mid-range phone over Wi-Fi it is long
// enough to photograph, which is exactly what happened. Testers should see
// the build, not the compiler.
//
// Node built-ins only — nothing to install, nothing to keep up to date.
import { createServer as createHttpsServer } from "node:https";
import { request as httpRequest } from "node:http";
import { readFileSync } from "node:fs";

const PORT = Number(process.env.PROXY_PORT || 3010);
const TARGET_PORT = Number(process.env.TARGET_PORT || 3011);
const HOST = process.env.PROXY_HOST || "0.0.0.0";

const options = {
  key: readFileSync(process.env.SSL_KEY_FILE),
  cert: readFileSync(process.env.SSL_CERT_FILE),
};

const server = createHttpsServer(options, (req, res) => {
  const upstream = httpRequest(
    {
      host: "127.0.0.1",
      port: TARGET_PORT,
      method: req.method,
      path: req.url,
      headers: {
        ...req.headers,
        host: `127.0.0.1:${TARGET_PORT}`,
        // Next needs to know the original scheme, or any absolute URL it
        // generates comes back http and the browser blocks it as mixed
        // content on a page it just served over TLS.
        "x-forwarded-proto": "https",
        "x-forwarded-host": req.headers.host ?? "",
      },
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers);
      upstreamRes.pipe(res, { end: true });
    },
  );

  upstream.on("error", (err) => {
    // A dead upstream must say so rather than hanging until the phone gives
    // up, which looks identical to a network problem from the tester's side.
    res.writeHead(502, { "content-type": "text/plain" });
    res.end(`Upstream Next server on :${TARGET_PORT} is not answering.\n${err.message}\n`);
  });

  req.pipe(upstream, { end: true });
});

// Next's client uses a websocket for navigation state even in production
// builds; without this it silently degrades to full page loads.
server.on("upgrade", (req, socket, head) => {
  const upstream = httpRequest({
    host: "127.0.0.1",
    port: TARGET_PORT,
    method: req.method,
    path: req.url,
    headers: { ...req.headers, host: `127.0.0.1:${TARGET_PORT}` },
  });
  upstream.end();
  upstream.on("upgrade", (upstreamRes, upstreamSocket, upstreamHead) => {
    const head_ = [
      `HTTP/1.1 101 Switching Protocols`,
      ...Object.entries(upstreamRes.headers).map(([k, v]) => `${k}: ${v}`),
      "", "",
    ].join("\r\n");
    socket.write(head_);
    if (upstreamHead?.length) socket.unshift(upstreamHead);
    upstreamSocket.pipe(socket).pipe(upstreamSocket);
  });
  upstream.on("error", () => socket.destroy());
  if (head?.length) socket.unshift(head);
});

server.listen(PORT, HOST, () => {
  console.log(`HTTPS proxy on ${HOST}:${PORT} -> 127.0.0.1:${TARGET_PORT}`);
});
