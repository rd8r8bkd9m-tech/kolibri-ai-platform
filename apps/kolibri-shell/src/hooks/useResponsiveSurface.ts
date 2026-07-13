import { useEffect, useState } from 'react';

const MOBILE_QUERY = '(max-width: 720px)';

function currentMatches(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches;
}

export function useResponsiveSurface(): 'mobile' | 'desktop' {
  const [mobile, setMobile] = useState(currentMatches);

  useEffect(() => {
    const query = window.matchMedia(MOBILE_QUERY);
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return mobile ? 'mobile' : 'desktop';
}
