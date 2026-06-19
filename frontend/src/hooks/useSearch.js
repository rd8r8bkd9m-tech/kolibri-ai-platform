import { useState } from "react"

export function useSearch({ API_BASE }) {
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    try {
      const r = await fetch(`${API_BASE}/rag/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, limit: 5 }),
      })
      if (!r.ok) { setSearchResults([]); setSearchLoading(false); return }
      const d = await r.json()
      setSearchResults(d.results || [])
    } catch { setSearchResults([]) }
    setSearchLoading(false)
  }

  return { searchQuery, setSearchQuery, searchResults, searchLoading, handleSearch }
}
