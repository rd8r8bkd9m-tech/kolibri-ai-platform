import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { App } from '../src/app/App';
import { FakeKolibriClient } from '../src/test/FakeKolibriClient';

describe('mobile surface', () => {
  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
  });

  it('uses one-scroller mobile composition and presents history as a sheet', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    const user = userEvent.setup();
    render(<App client={new FakeKolibriClient()} />);
    await screen.findByPlaceholderText('Уточнить или изменить...');

    expect(document.querySelector('.kolibri-shell')).toHaveAttribute('data-surface', 'mobile');
    expect(document.querySelectorAll('.conversation-scroll')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Открыть историю' }));
    expect(screen.getByRole('dialog', { name: 'История проектов' })).toHaveAttribute('data-presentation', 'sheet');
  });

  it('new conversation closes the sheet and clears the current turn', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    const user = userEvent.setup();
    render(<App client={new FakeKolibriClient()} />);
    await user.type(await screen.findByRole('textbox', { name: 'Сообщение' }), 'Первый запрос');
    await user.click(screen.getByRole('button', { name: 'Отправить' }));
    expect(await screen.findByText('Первый запрос')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Открыть историю' }));
    const history = screen.getByRole('dialog', { name: 'История проектов' });
    await user.click(within(history).getByRole('button', { name: 'Новый диалог' }));
    expect(screen.queryByText('Первый запрос')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'История проектов' })).not.toBeInTheDocument();
  });
});
