# Official MCP Registry (`mcp_registry`)

Source plug-in for the [Official MCP Registry](https://registry.modelcontextprotocol.io) (`https://registry.modelcontextprotocol.io/v0/servers`).

## Reuse terms and licence

- **Catalog repository:** [`modelcontextprotocol/registry`](https://github.com/modelcontextprotocol/registry), licensed under Apache-2.0 / MIT (documentation under CC-BY-4.0; see its [LICENSE](https://github.com/modelcontextprotocol/registry/blob/main/LICENSE)).
- **Downstream reuse:** The registry's [ecosystem vision](https://github.com/modelcontextprotocol/registry/blob/main/docs/design/ecosystem-vision.md) explicitly designates `registry.modelcontextprotocol.io` as the canonical public metadata source for downstream clients, aggregators, marketplaces, and subregistries, and expects automated ETL jobs to pull from its public API.
- **No login or scraping:** Uses only public `GET https://registry.modelcontextprotocol.io/v0/servers?limit=100&version=latest` API calls and public GitHub GraphQL metadata reads (`licenseInfo`, `stargazerCount`, `isArchived`, `isPrivate`, `isFork`, `description`).
- **Summaries and attribution:** Every listing is tagged `public-source` and `mcp-server` with `status: "listed"` and `publisher: "openwizdev"`. Summaries are written fresh in plain English (never copied from the registry or repository description). Each listing links back to the Official MCP Registry search entry and to the repository's licence file (or repository URL when no licence is stated).

## Filtering and sharding

- Keeps only entries where `_meta["io.modelcontextprotocol.registry/official"]` has `isLatest == true` and `status == "active"`.
- Drops entries with:
  - no public GitHub `repository.url` and no resolving `websiteUrl`;
  - an archived, private, missing, or empty-description fork GitHub repository;
  - empty, placeholder, or test/example/hello-world/template names or descriptions;
  - duplicate normalised URLs (or URLs/ids already present in `listings/`).
- Sharding (when run in parallel across 16 shards): `int(sha1(norm_url).hexdigest(), 16) % 16`, where `norm_url` is `'https://' + host.lower().removeprefix('www.') + path` with a trailing `/` and then a trailing `.git` removed, query and fragment dropped, and scheme always `https://`.
