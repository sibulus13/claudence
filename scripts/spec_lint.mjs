// Bounded helper for spec_check.py: markdownlint rule MD043 (required headings, CK-4) and the Mermaid parser (CK-6, CK-15, CK-22).
//   node spec_lint.mjs < {"headings":[{"key","text","heading"}], "diagrams":[{"key","text"}]}
//   stdout: {"headings":{key:{ok,detail}}, "diagrams":{key:{ok,type,actors,subgraphs,error}}}
// Each heading unit lints `text` against MD043 with ["*", "## <heading>", "*"], so a heading is either there or not.
import { lint } from "markdownlint-cli2/markdownlint/promise";

const input = JSON.parse(await new Promise((resolve) => {
  let data = "";
  process.stdin.on("data", (c) => (data += c)).on("end", () => resolve(data));
}));
const out = { headings: {}, diagrams: {} };

for (const unit of input.headings ?? []) {
  const config = { default: false, MD043: { headings: ["*", `## ${unit.heading}`, "*"], match_case: false } };
  const result = (await lint({ strings: { doc: unit.text }, config })).doc;
  out.headings[unit.key] = { ok: result.length === 0, detail: result.map((r) => `${r.ruleNames[0]} ${r.ruleDescription}`).join("; ") };
}

if ((input.diagrams ?? []).length) {
  const { JSDOM } = await import("jsdom");
  const dom = new JSDOM("<!doctype html><html><body></body></html>");
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  const mermaid = (await import("mermaid")).default;
  for (const unit of input.diagrams) {
    try {
      const { diagramType } = await mermaid.parse(unit.text);
      const diagram = await mermaid.mermaidAPI.getDiagramFromText(unit.text);
      const actors = diagramType === "sequence" ? [...diagram.db.getActors().keys()] : [];
      const subgraphs = diagramType.startsWith("flowchart") ? diagram.db.getSubGraphs().map((s) => s.title) : [];
      out.diagrams[unit.key] = { ok: true, type: diagramType, actors, subgraphs, error: "" };
    } catch (e) {
      out.diagrams[unit.key] = { ok: false, type: "", actors: [], subgraphs: [], error: String(e.message ?? e).split("\n")[0] };
    }
  }
}
process.stdout.write(JSON.stringify(out));
process.exit(0);
