import { TOOLS } from "./constants.js";

// The local catalog provides labels and icons only.  Visibility is controlled
// exclusively by the server's fail-closed public projection, which contains
// available records and no operator-only reason codes.
export function availableTools(capabilities = [], catalog = TOOLS) {
  const enabled = new Set(
    (Array.isArray(capabilities) ? capabilities : [])
      .filter((item) => (
        item?.object === "product.capability"
        && item?.surface === "tool"
        && item?.status === "available"
        && item?.available === true
      ))
      .map((item) => item.id),
  );
  return catalog.filter((tool) => enabled.has(tool.id));
}
