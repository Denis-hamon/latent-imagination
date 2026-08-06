# Gate adapters — enumerated surfaces (story 5.1, FR-25/NFR-V1)

Only vendor-documented interception surfaces. Two distinct setups per FR-25
(different harness AND different model vendor):

| # | Adapter | Surface (documented by vendor) | Vendor/model axis |
|---|---|---|---|
| 1 | `claude-code-hooks` | Claude Code **PreToolUse** hooks (JSON stdin contract, documented lifecycle) | Anthropic models |
| 2 | `mcp-gateway` | MCP (Model Context Protocol) gateway interception point — the protocol's documented message path | any MCP-capable CLI on a DIFFERENT vendor |

Both adapters plug the sole seam: `gate.intercept.annotate` (in) + decision log (out).
Advisory only — neither adapter carries a blocking code path (FR-19; FR-21's blocking
belongs to a later phase with measured-precision certificates).

The 4.1 harvest machinery's robots/politeness discipline applies to any doc fetching.
