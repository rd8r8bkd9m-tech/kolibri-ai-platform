import { useEffect, useState } from "react"

export function usePwaStatus() {
  const [status, setStatus] = useState("проверка")

  useEffect(() => {
    const installed = window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone
    if (!("serviceWorker" in navigator)) {
      setStatus("не поддерживается")
      return
    }
    setStatus(installed ? "установлено" : "готово к установке")
  }, [])

  return status
}
