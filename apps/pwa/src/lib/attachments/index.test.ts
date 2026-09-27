import { describe, expect, it } from 'vitest';

import { attachmentKind, pendingShell, prepareAttachment } from './index';

describe('pièces jointes Office éditables', () => {
  for (const [name, type] of [
    ['budget.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    ['contrat.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    ['presentation.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'],
  ]) {
    it(`accepte ${name} comme document`, () => {
      const file = new File(['binary'], name, { type });

      expect(attachmentKind(file)).toBe('document');
    });
  }

  it('prépare un XLSX sans le décoder comme du texte brut', async () => {
    const file = new File(
      [new Uint8Array([0, 255, 1, 2, 3])],
      'budget.xlsx',
      { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    );
    const shell = pendingShell(file);

    const prepared = await prepareAttachment(shell);

    expect(prepared.status).toBe('ready');
    expect(prepared.metadata?.format).toBe('XLSX');
    expect(prepared.extractedText).toBeUndefined();
  });
});
