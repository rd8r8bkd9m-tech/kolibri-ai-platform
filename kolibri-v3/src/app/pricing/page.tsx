import { redirect } from 'next/navigation';

/**
 * Pricing has one canonical presentation on the public landing page.
 * Keep /pricing as a stable deep link for navigation, bookmarks, and SEO
 * integrations while preserving the landing page as the source of truth.
 */
export default function PricingPage() {
  redirect('/#pricing');
}
