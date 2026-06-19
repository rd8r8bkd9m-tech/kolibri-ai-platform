import { useState, useCallback } from "react"

export function useWebSocket({ setMessages, setLoading }) {
  const [ws, setWs] = useState(null)
  const [connected, setConnected] = useState(false)

  const connectWS = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    let socket
    const wsHost = window.location.host
    const token = localStorage.getItem("kolibri_access_token") || ""
    const wsUrl = `${proto}//${wsHost}/ws/chat${token ? `?token=${token}` : ""}`
    try { socket = new WebSocket(wsUrl) } catch { return }

    let retryDelay = 1000
    const maxDelay = 30000

    socket.onopen = () => { setConnected(true); retryDelay = 1000 }
    socket.onclose = (e) => {
      setConnected(false)
      if (e.code !== 4001) {
        const delay = Math.min(retryDelay, maxDelay)
        retryDelay = Math.min(retryDelay * 2, maxDelay)
        setTimeout(connectWS, delay)
      }
    }
    socket.onerror = () => { socket.close() }
    socket.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.streaming) {
        setMessages(prev => {
          const n = [...prev]
          const last = n[n.length - 1]
          if (last && last.role === "assistant" && last.streaming) last.content += data.chunk || ""
          return [...n]
        })
      } else if (data.done || data.response) {
        setMessages(prev => {
          const n = [...prev]
          const last = n[n.length - 1]
          if (last && last.role === "assistant" && last.streaming) {
            last.content = data.response || last.content || ""
            last.provider = data.provider
            last.streaming = false
            if (data.canvas) last.canvas = data.canvas
          }
          return [...n]
        })
        setLoading(false)
      }
    }
    setWs(socket)
  }, [setMessages, setLoading])

  return { ws, connected, connectWS }
}
