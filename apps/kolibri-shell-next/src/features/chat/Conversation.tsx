import type { ChatMessage } from "@domain/shell";
import { CheckCheck, RefreshCw } from "lucide-react";

interface ConversationProps {
  messages: ChatMessage[];
}

function Message({ message }: { message: ChatMessage }) {
  const isUser = message.author === "user";
  return (
    <article className={`chat-message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-meta">
        <span>{isUser ? "Вы" : "Kolibri"}, сегодня в {message.sentAt}</span>
      </div>
      <div className="message-content">
        {message.content.split("\n").map((line, index) => (
          <span key={`${message.id}-${index}`}>
            {line}
            {index < message.content.split("\n").length - 1 ? <br /> : null}
          </span>
        ))}
        <span className="mobile-message-state">
          {message.sentAt}
          {isUser ? (
            message.delivery === "failed" ? (
              <RefreshCw aria-label="Не отправлено" />
            ) : (
              <CheckCheck aria-label={message.delivery === "sending" ? "Отправляется" : "Отправлено"} />
            )
          ) : null}
        </span>
      </div>
    </article>
  );
}

export function Conversation({ messages }: ConversationProps) {
  return (
    <section className="conversation" aria-label="Чат">
      {messages.map((message) => <Message key={message.id} message={message} />)}
    </section>
  );
}
