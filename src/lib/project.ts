import type { FontProject, GlyphSource } from './types';

export function safeProjectId(): string {
  return `project_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`;
}

export function createEmptyProject(familyName: string): FontProject {
  const now = new Date().toISOString();
  return {
    schemaVersion: 1,
    id: safeProjectId(),
    familyName: familyName.trim() || 'Untitled Hand',
    description: '',
    createdAt: now,
    updatedAt: now,
    unitsPerEm: 1000,
    ascender: 800,
    descender: -200,
    capHeight: 700,
    xHeight: 500,
    lineGap: 100,
    styles: [{
      id: 'regular',
      name: 'Regular',
      fontWeight: 400,
      fontStyle: 'normal',
      glyphs: createUppercaseGlyphs(),
      kerningPairs: [],
      defaultSpaceWidth: 250,
      defaultLeftBearing: 40,
      defaultRightBearing: 40,
    }],
    templates: [],
  };
}

function createUppercaseGlyphs(): GlyphSource[] {
  return Array.from({ length: 26 }, (_, index) => {
    const character = String.fromCharCode(65 + index);
    return {
      id: `regular_uni${character.charCodeAt(0).toString(16).padStart(4, '0').toUpperCase()}`,
      glyphName: character,
      character,
      unicode: character.charCodeAt(0),
      sourceType: 'individual-upload',
      transform: { scaleX: 1, scaleY: 1, translateX: 0, translateY: 0, rotation: 0 },
      metrics: { advanceWidth: 600, leftSideBearing: 40, rightSideBearing: 40 },
      processing: { threshold: 170, invert: false, smoothing: 1, despeckle: 8, cropPadding: 12, tracePreset: 'balanced' },
      status: 'missing',
    };
  });
}
