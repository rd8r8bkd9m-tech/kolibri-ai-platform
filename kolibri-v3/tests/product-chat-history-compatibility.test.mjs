import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const contracts = await import(
  pathToFileURL(path.join(APP_ROOT, "lib/product-chat/contracts.ts")).href
);

const threadId = "thread_history_compatibility01";
const timestamp = "2026-07-29T03:23:28.965695+00:00";

const toolPart = (overrides = {}) => ({
  type: "tool-call",
  toolCallId: "tool_history_compatibility01",
  toolName: "present_estimate",
  args: { projectId: "project_history_compatibility01", version: 1 },
  argsText: JSON.stringify({
    projectId: "project_history_compatibility01",
    version: 1,
  }),
  result: { rendered: true },
  ...overrides,
});

const message = (id, part) => ({
  id,
  role: "assistant",
  content: [part],
  createdAt: timestamp,
  status: { type: "complete", reason: "stop" },
  submittedFeedback: null,
});

const page = (...messages) => ({
  threadId,
  messages,
  nextCursor: null,
});

test("history parser normalizes canonical, string, and one-sided tool args", () => {
  const canonicalArgs = {
    projectId: "project_history_compatibility01",
    nested: { enabled: true, values: [1, 2] },
  };
  const historicalPage = page(
    message(
      "message_history_object_args01",
      toolPart({
        args: canonicalArgs,
        argsText:
          '{"nested":{"values":[1,2],"enabled":true},"projectId":"project_history_compatibility01"}',
      }),
    ),
    message(
      "message_history_missing_text01",
      toolPart({ args: canonicalArgs, argsText: undefined }),
    ),
    message(
      "message_history_missing_args01",
      toolPart({
        args: undefined,
        argsText: JSON.stringify(canonicalArgs),
      }),
    ),
    message(
      "message_history_string_args01",
      toolPart({
        args: JSON.stringify(canonicalArgs),
        argsText: undefined,
      }),
    ),
  );
  const parsed = contracts.parseProductChatMessagePage(
    {
      ...historicalPage,
      messages: historicalPage.messages.map((entry) => ({
        ...entry,
        content: entry.content.map((part) =>
          Object.fromEntries(
            Object.entries(part).filter(([, value]) => value !== undefined),
          ),
        ),
      })),
    },
    threadId,
  );

  for (const entry of parsed.messages) {
    const [part] = entry.content;
    assert.deepEqual(part.args, canonicalArgs);
    assert.deepEqual(JSON.parse(part.argsText), canonicalArgs);
  }
});

test("history parser accepts only the documented EstimateEditor provenance alias drift", () => {
  const source = "document://chat-run/run_04tt1Fv";
  const currentArgs = {
    $type: "EstimateEditor",
    projectId: "project_history_compatibility01",
    rows: [
      {
        id: "row_history_compatibility01",
        enginePriceProvenance: { sourceUrl: source, sourceLabel: "Расчёт" },
      },
    ],
  };
  const historicalArgs = {
    ...currentArgs,
    rows: [
      {
        ...currentArgs.rows[0],
        enginePriceProvenance: { url: source, sourceLabel: "Расчёт" },
      },
    ],
  };

  const parsed = contracts.parseProductChatMessagePage(
    page(
      message(
        "message_history_source_alias01",
        toolPart({ args: currentArgs, argsText: JSON.stringify(historicalArgs) }),
      ),
    ),
    threadId,
  );
  const [part] = parsed.messages[0].content;

  assert.deepEqual(part.args, currentArgs);
  assert.deepEqual(JSON.parse(part.argsText), currentArgs);
});

test("history stores EstimateEditor 1.4 as a compact document reference", () => {
	const compact = {
		$type: "EstimateEditor",
		schemaVersion: "1.4",
		projectId: "project_history_compatibility01",
		documentId: "document_history_compatibility01",
		version: 7,
		rows: [],
		rowPage: { offset: 0, limit: 0, totalRows: 12_480, hasMore: true },
	};
	const parsed = contracts.parseProductChatMessagePage(
		page(
			message(
				"message_history_estimate_reference01",
				toolPart({ args: compact, argsText: JSON.stringify(compact) }),
			),
		),
		threadId,
	);
	assert.deepEqual(parsed.messages[0].content[0].args, compact);
	assert.throws(
		() =>
			contracts.parseProductChatMessagePage(
				page(
					message(
						"message_history_estimate_inline01",
						toolPart({
							args: { ...compact, rows: [{ id: "row_inline_12345678" }] },
							argsText: JSON.stringify({
								...compact,
								rows: [{ id: "row_inline_12345678" }],
							}),
						}),
					),
				),
				threadId,
			),
		contracts.ProductChatContractError,
	);
});

test("history parser still rejects malformed or conflicting tool arguments", () => {
  const invalidParts = [
    toolPart({ args: undefined, argsText: undefined }),
    toolPart({ args: "[]", argsText: undefined }),
    toolPart({ args: "{broken", argsText: undefined }),
    toolPart({ args: { version: 1 }, argsText: '{"version":2}' }),
    toolPart({ args: { nested: undefined }, argsText: undefined }),
    toolPart({ unexpected: true }),
    toolPart({ result: undefined }),
    toolPart({
      args: { $type: "OtherWidget", sourceUrl: "safe" },
      argsText: '{"$type":"OtherWidget","url":"safe"}',
    }),
  ];

  for (const [index, part] of invalidParts.entries()) {
    const cleanPart = Object.fromEntries(
      Object.entries(part).filter(([, value]) => value !== undefined),
    );
    assert.throws(
      () =>
        contracts.parseProductChatMessagePage(
          page(
            message(
              `message_history_invalid_${String(index).padStart(2, "0")}`,
              cleanPart,
            ),
          ),
          threadId,
        ),
      contracts.ProductChatContractError,
    );
  }
});
