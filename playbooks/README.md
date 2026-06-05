# playbooks/ — per-industry customization layer

One markdown file per industry. Playbooks are DOMAIN KNOWLEDGE (what good looks like
for this kind of business); templates stay STRUCTURE and skills stay PROCEDURE.

## Install (one time)
Drop this folder into ~/web-studio/ then tell Claude Code:
  "Wire the playbook system into the studio per playbooks/README.md"
Claude should then:
1. Add to CLAUDE.md (under its own heading, before Hard rules):
   ## Industry playbooks
   When assembling a prototype or finishing a client, ALWAYS check playbooks/ for a file
   matching the client's industry (from brief.yaml `industry:`, or inferred from the
   baseline if blank — record the inference). If a match exists, read it and apply it to
   content drafting, schema, section choices, and tone. If none exists, say so explicitly,
   proceed with general defaults, and suggest creating one from playbooks/_TEMPLATE.md.
2. Add `industry: ""` to templates/intake-template/brief.yaml under `client:` with a
   comment listing available playbooks.
3. Commit.

## Authoring a new playbook
Copy _TEMPLATE.md to <industry>.md and fill it in — or, better, tell Claude Code:
"Create a playbook for <industry> using _TEMPLATE.md; research what their buyers
look for." Review what it drafts; the playbook then applies to every future client
in that industry. Keep each file under ~150 lines: playbooks are read in full at
apply time.
