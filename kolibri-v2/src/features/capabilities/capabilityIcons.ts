import {
  AppWindow,
  Blocks,
  Calculator,
  Code2,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Globe2,
  Image as ImageIcon,
  Monitor,
  PanelsTopLeft,
  Presentation,
  WandSparkles,
  type LucideIcon,
} from 'lucide-react'
import type { UiCapabilityKey } from './types'

/**
 * One exhaustive icon registry for every capability the Shell can expose.
 * Keeping this next to the capability contract makes adding a visible tool a
 * compile-time operation instead of allowing desktop and mobile menus to
 * silently diverge.
 */
export const capabilityIcons: Record<UiCapabilityKey, LucideIcon> = {
  'estimate.create': Calculator,
  'document.editor': FileText,
  'web.search': Globe2,
  'file.search': FileSearch,
  'document.pdf': FileText,
  'document.docx': FileText,
  'document.xlsx': FileSpreadsheet,
  'document.pptx': Presentation,
  'code.execute': Code2,
  'image.generate': ImageIcon,
  'image.edit': WandSparkles,
  'site.create': PanelsTopLeft,
  'app.create': AppWindow,
  'browser.use': Monitor,
  'mcp.invoke': Blocks,
}
