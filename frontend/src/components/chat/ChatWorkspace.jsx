import { MessageList } from "./MessageList"
import { WelcomeState } from "./WelcomeState"
import { ChatComposer } from "./ChatComposer"

export function ChatWorkspace({
  messages,
  messagesEndRef,
  inputRef,
  input,
  loading,
  onInputChange,
  onSend,
  onPrompt,
  onControl,
  onFocus,
  onBlur,
  variant = "app",
}) {
  return (
    <div className={`chat-container chat-container--${variant}`}>
      <div className="messages">
        {messages.length === 0 && <WelcomeState onPrompt={onPrompt} onControl={onControl} />}
        <MessageList messages={messages} messagesEndRef={messagesEndRef} />
      </div>
      <ChatComposer
        inputRef={inputRef}
        value={input}
        loading={loading}
        onChange={onInputChange}
        onSend={onSend}
        onFocus={onFocus}
        onBlur={onBlur}
      />
    </div>
  )
}
