import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { EstimateArtifactData, VerifiedArtifact } from '../src/api/types';
import { EstimateWorkspace } from '../src/components/EstimateWorkspace';

function artifact(): VerifiedArtifact & { estimate: EstimateArtifactData } {
  return {
    id: 'estimate-test',
    name: 'Смета_дом.pdf',
    mimeType: 'application/pdf',
    sizeBytes: 4096,
    sha256: 'f'.repeat(64),
    downloadUrl: '/v1/artifacts/estimate-test/content',
    kind: 'estimate',
    estimate: {
      title: 'Предварительная смета',
      location: 'Лениногорск',
      pricedAt: '12.07.2026',
      status: 'verified',
      sourceSummary: 'Источники проверены',
      lines: [
        { id: 'foundation', title: 'Фундамент', unit: 'м³', quantity: 2, unitPriceRub: 100, amountRub: 200 },
      ],
      summarySections: [
        { id: 'foundation', title: 'Фундамент', amountRub: 200, icon: 'foundation' },
      ],
    },
  };
}

describe('typed estimate workspace', () => {
  it('uses spinner-free editable inputs and deterministically recalculates totals', async () => {
    const user = userEvent.setup();
    render(<EstimateWorkspace artifact={artifact()} presentation="desktop" />);

    const quantity = screen.getByRole('textbox', { name: 'Количество, строка 1' });
    expect(quantity).toHaveAttribute('type', 'text');
    expect(quantity).toHaveAttribute('inputmode', 'decimal');
    await user.clear(quantity);
    await user.type(quantity, '3');
    expect(screen.getByText('300 ₽')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Источники' }));
    expect(screen.getAllByText('Источники проверены')).toHaveLength(2);
    expect(screen.getByRole('link', { name: /Смета_дом.pdf/ })).toHaveAttribute(
      'href',
      '/v1/artifacts/estimate-test/content',
    );
  });

  it('presents the mobile summary and opens editing as a full-screen dialog', async () => {
    const user = userEvent.setup();
    render(<EstimateWorkspace artifact={artifact()} presentation="mobile" />);

    expect(screen.getByText('Предварительная смета')).toBeVisible();
    await user.click(screen.getByRole('button', { name: /Редактировать/ }));
    expect(screen.getByRole('dialog', { name: 'Редактор сметы' })).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Количество, строка 1' })).toHaveAttribute('type', 'text');
    await user.click(screen.getByRole('button', { name: 'Закрыть редактор' }));
    expect(screen.queryByRole('dialog', { name: 'Редактор сметы' })).not.toBeInTheDocument();
  });
});
