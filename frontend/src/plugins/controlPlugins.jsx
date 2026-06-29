import { BillingPanel } from "../components/control/BillingPanel"
import { ClusterPanel } from "../components/control/ClusterPanel"
import { DocumentsPanel } from "../components/control/DocumentsPanel"
import { SearchPanel } from "../components/control/SearchPanel"
import { SettingsPanel } from "../components/control/SettingsPanel"

export const controlPlugins = [
  {
    id: "billing.tbank",
    tab: "billing",
    title: "Подписки",
    surface: "control",
    capabilities: ["billing.checkout", "billing.recurrent", "provider.tbank"],
    render: ({ billing }) => (
      <BillingPanel
        plansState={billing.plans}
        form={billing.form}
        setForm={billing.setForm}
        loading={billing.loading}
        message={billing.message}
        onSubmit={billing.onSubmit}
      />
    ),
  },
  {
    id: "knowledge.documents",
    tab: "docs",
    title: "Документы",
    surface: "control",
    capabilities: ["knowledge.upload", "documents.preview"],
    render: ({ documents }) => (
      <DocumentsPanel
        documents={documents.items}
        docLoading={documents.loading}
        docError={documents.error}
        uploading={documents.uploading}
        fileInputRef={documents.fileInputRef}
        onUpload={documents.onUpload}
      />
    ),
  },
  {
    id: "knowledge.search",
    tab: "search",
    title: "Поиск",
    surface: "control",
    capabilities: ["knowledge.search", "rag.query"],
    render: ({ search }) => (
      <SearchPanel
        query={search.query}
        setQuery={search.setQuery}
        results={search.results}
        loading={search.loading}
        onSearch={search.onSearch}
      />
    ),
  },
  {
    id: "factory.cluster",
    tab: "cluster",
    title: "Сеть",
    surface: "control",
    capabilities: ["factory.status", "nodes.health"],
    render: ({ cluster }) => <ClusterPanel status={cluster.status} onRefresh={cluster.onRefresh} />,
  },
  {
    id: "app.settings",
    tab: "settings",
    title: "Тема",
    surface: "control",
    capabilities: ["theme.system", "pwa.status"],
    render: ({ settings }) => (
      <SettingsPanel
        theme={settings.theme}
        setTheme={settings.setTheme}
        resolvedTheme={settings.resolvedTheme}
        pwaStatus={settings.pwaStatus}
      />
    ),
  },
]

export function getControlPlugin(tab) {
  return controlPlugins.find(plugin => plugin.tab === tab) || controlPlugins[0]
}
