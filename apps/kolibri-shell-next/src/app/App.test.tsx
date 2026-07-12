import { App } from "@app/App";
import type { ShellSnapshot } from "@domain/shell";
import type { ShellClient } from "@services/shellClient";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const snapshot: ShellSnapshot = {
  project: { id: "project-test", title: "Дом 100 м²", location: "Лениногорск" },
  messages: [{ id: "welcome", author: "assistant", content: "Готово.", sentAt: "11:42", delivery: "sent" }],
  trace: {
    id: "trace-test",
    status: "completed",
    stages: [
      { id: "one", label: "Понял задачу", state: "done" },
      { id: "two", label: "Подготовил результат", state: "done" },
    ],
    agents: [],
  },
  estimate: {
    id: "estimate-test",
    title: "Предварительная смета · дом 100 м²",
    location: "Лениногорск",
    pricedAt: "12.07.2026",
    sourceSummary: "проверенные базы",
    fileName: "estimate.pdf",
    fileSizeLabel: "PDF · 1 КБ",
    lines: [{ id: "foundation", kind: "foundation", label: "Фундамент", unit: "м³", quantity: 2, unitPrice: 100 }],
  },
  activeResponseId: null,
};

function client(): ShellClient {
  return {
    async start(emit) {
      emit({ type: "snapshot", snapshot });
      return () => undefined;
    },
    async send(input, emit) {
      emit({ type: "message.delivery", id: input.clientMessageId, delivery: "sent" });
      emit({
        type: "message.added",
        message: { id: "reply", author: "assistant", content: "Принято.", sentAt: "11:43", delivery: "sent" },
      });
    },
  };
}

describe("primary shell controls", () => {
  it("opens the single bird/menu slot, sources and fullscreen artifact", async () => {
    const user = userEvent.setup();
    render(<App client={client()} />);
    await screen.findByText("Готово.");

    await user.click(screen.getByRole("button", { name: "Открыть меню" }));
    const navigation = screen.getByRole("dialog", { name: "Kolibri" });
    expect(navigation).toBeInTheDocument();
    await user.click(within(navigation).getByRole("button", { name: "Закрыть" }));

    await user.click(screen.getAllByRole("button", { name: "Источники" })[0]!);
    const sources = screen.getByRole("dialog", { name: "Источники сметы" });
    expect(sources).toBeInTheDocument();
    await user.click(within(sources).getByRole("button", { name: "Закрыть" }));

    await user.click(screen.getByRole("button", { name: "Открыть окном" }));
    expect(screen.getByRole("dialog", { name: "Предварительная смета" })).toBeInTheDocument();
  });

  it("edits a derived total, prints and sends a message", async () => {
    const user = userEvent.setup();
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    render(<App client={client()} />);
    await screen.findByText("Готово.");

    await user.click(screen.getAllByRole("button", { name: "Редактировать" })[0]!);
    const price = screen.getByRole("textbox", { name: "Цена: Фундамент" });
    await user.clear(price);
    await user.type(price, "250");
    expect(screen.getAllByText(/500 ₽/).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: "PDF" })[0]!);
    expect(print).toHaveBeenCalledOnce();

    await user.type(screen.getByRole("textbox", { name: "Сообщение" }), "Уточни стоимость");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    await waitFor(() => expect(screen.getByText("Принято.")).toBeInTheDocument());
  });
});
