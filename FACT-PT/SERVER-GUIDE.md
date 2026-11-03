# Deploying FACT-PT on a server

For a Linux server with Docker, reached by others over the internet or an internal network, with
the site served over **HTTPS** by a reverse proxy on the same machine. For trying it on a laptop or
desktop, the [README](README.md) is enough.

What runs, all from `docker-compose.yml`:

- `web` — the website, the only container with a published port. Here it is published on
  `127.0.0.1` only: the reverse proxy reaches it, nobody else does.
- `worker`, `redis`, `inference` — the queue, the runs and the models, on Docker's own network,
  with no port on the host.
- the **reverse proxy** (Caddy or nginx, installed on the host) — holds the certificate, answers on
  ports 80 and 443, and passes requests on to `127.0.0.1:8000`.

## What the server needs

- Linux with **Docker Engine** and the **Compose plugin** (`docker compose version`).
- **Disk**: about 3 GB for the models ([MODELS.md](MODELS.md)), plus the images.
- An **NVIDIA GPU** if there is one, with the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/):
  `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi` should list it.
  Without one the site works, slowly (minutes per stage).
- The **Modal gateway of the AMALIA models**, or an OpenAI-compatible server of your own (vLLM)
  that this one can reach: [MODELS.md](MODELS.md#behind-the-api) says what it serves and how.
- An **OpenRouter** account and key, for the Gemma writer
  ([MODELS.md](MODELS.md#gemma-on-openrouter)).
- The **VPN to the LUSA API**: the API only answers over it. Without it the worked examples still
  play, but a new claim stops before retrieval.
- A **domain name** pointing at the server, and ports **80 and 443** open to it, for the
  certificate. `facta.example.pt` below stands for it.

## 1. Get the code

```sh
git clone https://github.com/LIAAD/factapt.git
cd factapt/FACT-PT
```

## 2. Make `.env`

`.env` is not in git. Start from the example:

```sh
cp .env.example .env
```

and set, in it:

- **the LUSA account**: `API_URL_LUSA`, `USER_LUSA`, `PASSWORD_LUSA`.
- **the first administrator and the session secret**: `ADMIN_PASSWORD_HASH` and `SESSION_SECRET`.
  Copy both from another machine's `.env`, or make new ones (the build takes a few minutes):

  ```sh
  docker build -t facta-pt-web:1.6.0 web
  docker run --rm -it facta-pt-web:1.6.0 python -m app.acesso
  ```

  and paste the lines it prints, quotes included. The account is `admin`, or whatever
  `ADMIN_USERNAME` says. It is made on the first start, while there are no accounts; after that,
  the accounts live in `utilizadores.json` on the data volume and the administrator makes the rest
  in **Administração**. `ACCESS_PASSWORD_HASH`, from an older deployment, also makes that first
  administrator, and is not accepted for signing in afterwards.
- **`WEB_PORT=127.0.0.1:8000`**: publishes the website on the loopback interface only. Docker's
  published ports go around the host's firewall (ufw, firewalld), so with a bare `8000` the site
  would also answer over plain HTTP at `http://<server>:8000`, to anyone who can reach the machine.
- **no `COOKIE_SECURE=false` line**: behind HTTPS the session cookie must be Secure (the default),
  and the site then also sends HSTS.
- **the AMALIA models**: `MODAL_API_URL` and `MODAL_API_KEY`, the Modal gateway
  ([MODELS.md](MODELS.md#behind-the-api)); with a server of your own, `QG_API_*` and
  `AMALIA_API_*` instead, without `MODAL_API_URL`, where from the containers a server on this
  machine is `host.docker.internal`.
- **the Gemma writer**: `ARTICLE_API_KEY`, the OpenRouter key
  ([MODELS.md](MODELS.md#gemma-on-openrouter)).
- **the classifiers**: by default they are downloaded on the first start. To use a folder of local
  checkpoints instead (no download, works offline), follow
  [MODELS.md](MODELS.md#local-checkpoints). For an 8 GB card see [GPU-GUIDE.md](GPU-GUIDE.md).

Leave `FORWARDED_ALLOW_IPS` and `RUNS_PER_ADDRESS` alone for now: step 5 sets them. Leave
`CORS_ORIGINS` empty while the page and the API share the domain, as they do here. Leave
`RUN_STORE_DIR` alone too: the website and the worker share the run store's folder, `dados/`
beside the compose file (set `RUNS_DIR` to move it).

`chmod 600 .env`: it holds the LUSA password and the session secret.

## 3. Start

With an NVIDIA GPU:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Without one:

```sh
docker compose up -d --build
```

On a GPU server, use both `-f` files for every command below (`up`, `exec`, `logs`…); they are left
out here for brevity.

The first start downloads the classifiers, about 3 GB. The website answers at once, with the worked
examples; new claims once the models are loaded. Which ones are:

```sh
docker compose exec inference python -c "import urllib.request as u; print(u.urlopen('http://localhost:8100/health').read().decode())"
```

## 4. Put the reverse proxy in front

No domain of your own? [Without a domain: Tailscale Funnel](#without-a-domain-tailscale-funnel)
replaces this step.

The proxy has to pass the client's address on in `X-Forwarded-For`, and the scheme in
`X-Forwarded-Proto`. It must not buffer the responses: a verification is a server-sent event stream
that may stay open for hours. The website sends `X-Accel-Buffering: no` and a keep-alive line every
second, so the configurations below are all it takes.

**Caddy** (gets and renews the certificate by itself) — `/etc/caddy/Caddyfile`:

```caddy
facta.example.pt {
    reverse_proxy 127.0.0.1:8000
}
```

then `sudo systemctl reload caddy`.

**nginx** — a `server` block, with the certificate from certbot or your institution:

```nginx
server {
    listen 80;
    server_name facta.example.pt;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name facta.example.pt;

    ssl_certificate     /etc/letsencrypt/live/facta.example.pt/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/facta.example.pt/privkey.pem;

    # The website refuses bodies over 1 MiB itself; this keeps nginx in step.
    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

then `sudo nginx -t && sudo systemctl reload nginx`.

## 5. Trust the proxy, and only the proxy

The website reads the client's address from `X-Forwarded-For` only when the request comes from an
address in `FORWARDED_ALLOW_IPS`; from anyone else the header is ignored, or a client could pick its
own address and get round the sign-in throttle. Until this step, every visitor looks like the same
address: the sign-in throttle counts them together, and a few wrong passwords lock everyone out
for a while.

The proxy connects to `127.0.0.1:8000`, and Docker hands that connection to the container from the
gateway of the project's network. Find it:

```sh
docker network inspect facta-pt_facta-pt --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'
```

and put it in `.env` (the address is an example):

```sh
FORWARDED_ALLOW_IPS=172.18.0.1
```

With the real addresses believed, the per-address limit can be turned on as well, for example
`RUNS_PER_ADDRESS=2`. Apply both:

```sh
docker compose up -d web
```

The network, and so its gateway, keeps its address while it exists. `docker compose down` removes
it, and the next `up` may get another: after a `down`, run the command above again.

## 6. Check

- `https://facta.example.pt` opens, the password is asked once, and the session survives a reload.
- A worked example plays to the end.
- `curl -sI https://facta.example.pt | grep -i strict-transport` shows the HSTS header.
- `docker compose logs --tail 20 web`: the access lines show the visitors' addresses, not the
  gateway's.
- From another machine, `curl -m 5 http://<server>:8000` fails: the plain-HTTP port is not exposed.
- A new claim runs (with the VPN up), and the queue shows it while it does:
  `docker compose exec worker python -m app.fila`.

## Without a domain: Tailscale Funnel

For a machine with no domain name of its own and no ports open to the internet — a desktop behind
NAT, a Windows machine running Docker Desktop — [Tailscale](https://tailscale.com/) can put the site
on the internet instead of a proxy. `tailscaled` holds the certificate for the machine's `*.ts.net`
name, terminates TLS and passes the requests on to `127.0.0.1:8000`. Steps 1–3 are unchanged; this
section replaces step 4, and step 5 still applies.

What it needs, on the host that runs the containers:

- Tailscale installed and signed in: `tailscale status` lists the machine.
- **HTTPS certificates** enabled for the tailnet, on the admin console's DNS page.
- **Funnel** allowed for this machine: an ACL `nodeAttrs` grant of `funnel` to its tag, or to your
  user. `tailscale funnel` says where, the first time it is run without the grant. Scope it to this
  machine: it lets the holder serve any local port to the internet.

Publish the website on the loopback interface only, as step 2 says, so that the tunnel is the only
way in:

```sh
WEB_PORT=127.0.0.1:8000
```

Then put the site behind Funnel, on 443 — Funnel takes 443, 8443 and 10000, nothing else:

```sh
tailscale funnel --bg --https=443 http://127.0.0.1:8000
tailscale funnel status        # https://<machine>.<tailnet>.ts.net → 127.0.0.1:8000
```

`--bg` leaves it running after the shell closes, and it comes back with `tailscaled` after a reboot.
To close the site again, `tailscale funnel --https=443 off`: the address then stops answering.

**Trust the tunnel as the proxy** — step 5, with the same answer. Funnel connects from the host, and
Docker hands that connection to the web container from the gateway of the project's network, so the
container sees the gateway and not `127.0.0.1`: the addresses Funnel writes into `X-Forwarded-For`
are believed only once that gateway is in `FORWARDED_ALLOW_IPS`. Find it with step 5's
`docker network inspect`, then `docker compose up -d web`. With the real addresses in hand,
`RUNS_PER_ADDRESS=2` is worth turning on: otherwise one visitor can fill the queue, and until this is
done the sign-in throttle counts everyone as one address, so a few wrong passwords lock out every
visitor at once.

Leave `COOKIE_SECURE` at its default. Funnel serves the site over HTTPS, so the session cookie stays
`Secure` and `__Host-` prefixed, and the site sends HSTS.

Check, in place of step 6's first lines:

```sh
curl -sI https://<machine>.<tailnet>.ts.net | grep -i strict-transport
docker compose logs --tail 20 web      # the visitors' addresses, not the gateway's
```

Two things Funnel is not. It is **not a load balancer**: every visit goes through this machine's own
uplink, which sets how many people the site can serve. And it is **not a substitute for the password
gate**, which is now the only thing between the internet and the models; a run costs minutes of the
one worker, so `QUEUE_MAX` and `RUNS_PER_SESSION` (in `.env.example`) are the limits that matter.

| What you see | What to do |
|---|---|
| `tailscale funnel status` shows the route, but the address times out | Funnel is not allowed for this machine (the ACL grant above), or the tailnet has no HTTPS certificates. |
| The address answers 502 | Nothing is listening on `127.0.0.1:8000`: `docker compose ps`, and check that `WEB_PORT` publishes on the loopback. |
| The password is accepted but the next page asks again | `COOKIE_SECURE=false` was left in `.env` for plain HTTP: remove it, `docker compose up -d web`. |
| «Demasiadas tentativas falhadas» for everyone at once | Every visitor looks like one address: `FORWARDED_ALLOW_IPS` lacks the network's gateway (step 5). |

## Keeping it running

**After a reboot.** Every container has `restart: unless-stopped`, so they come back with Docker:
`sudo systemctl enable docker` makes sure Docker starts at boot. The VPN must come back too, or new
claims stop before retrieval.

**Updating.** Do not rebuild or restart while a run is under way: the run is lost. Check the queue,
then:

```sh
docker compose exec worker python -m app.fila    # nothing under way?
git pull
docker compose up -d --build
```

Use `up -d`, not `down` followed by `up`: `down` may change the gateway (step 5).

**The queue.** `docker compose exec worker python -m app.fila` lists the runs under way and waiting,
with the session and address that asked for each. `… python -m app.fila cancelar ID [ID …]` cancels
some, `… cancelar --todas` all of them. More runs at once, if the hardware allows:
`docker compose up -d --scale worker=2`.

**Changing the password.** Make new values (step 2), replace both lines in `.env`, then
`docker compose up -d web`. Everyone is signed out.

**Backups.** `.env` needs one, and the checkpoints folder if the models come from one. The
`modelos` volume can be downloaded again. The run store is an ordinary folder on the host,
`dados/` beside the compose file unless `RUNS_DIR` says otherwise, and it holds everything the
site accumulates: the last `RUN_RETENTION` (64) runs, for the citations of pages under way, which
are not meant to last; in `guardadas/`, every verification that ran to its end — the pages at
`/verificacao/<id>`, kept until `SAVED_RETENTION` (0, never) says otherwise; in `revisoes/`, the
editorial review of each of them; and, beside `execucoes/`, `utilizadores.json` and
`plataforma.json`. Copy the folder to back it all up. Each saved verification is one file, and
copying it back is enough to restore its address; anyone signed in who has an address can open
it. On a Linux host the folder must belong to the containers' user, `sudo chown -R 100:101 dados`,
or the site cannot write to it.

## If something does not fit

| What you see | What to do |
|---|---|
| The password is accepted but the next page asks again | The site is reached over plain HTTP, where a Secure cookie is not kept. Open it through the proxy, over HTTPS. |
| «Demasiadas tentativas falhadas» (too many failed attempts) for everyone at once | Every visitor looks like one address: `FORWARDED_ALLOW_IPS` is missing, or no longer the gateway (after a `docker compose down`). Redo step 5. |
| A verification stays on its first step, then shows everything at the end | Something buffers the stream: a proxy that drops `X-Accel-Buffering`, or a CDN in front. Turn its buffering off for the site. |
| Signing in or starting a run gives 411 | The proxy streams request bodies without `Content-Length`. nginx and Caddy as above do not. |
| A new claim stops before retrieval | The LUSA API is not reachable: check the VPN, and `API_URL_LUSA` and the account in `.env`. |
| New claims wait and never start | The models are not loaded yet (step 3's health check), or the worker is down: `docker compose ps`, `docker compose logs worker`. |
| The inference service runs out of memory | The server has less memory than the classifiers need: [GPU-GUIDE.md](GPU-GUIDE.md) for a small card. |
| The Gemma writer not available | `ARTICLE_API_KEY` is missing or wrong, or OpenRouter does not list `ARTICLE_API_MODEL`: `/health` and the inference log say which. |
