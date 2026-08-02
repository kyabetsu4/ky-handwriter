export type ViewId = 'home' | 'project' | 'template' | 'glyphs' | 'spacing' | 'kerning' | 'preview' | 'export';

export type TemplateGenerationResult = {
  success: boolean;
  outputs?: string[];
  templates?: unknown[];
  templateId?: string;
  pageCount?: number;
  warnings: string[];
  error?: string;
};

export type TemplateImportResult = {
  success: boolean;
  glyphs?: GlyphSource[];
  templateId?: string;
  pageNumber?: number;
  markerCount?: number;
  importedCount?: number;
  missingCount?: number;
  warnings: string[];
  error?: string;
};

export type CompileResult = {
  success: boolean;
  outputs?: string[];
  warnings: string[];
  glyphCount?: number;
  glyphBounds?: Record<string, { xMin: number; yMin: number; xMax: number; yMax: number; outlineWidth: number; measurementVersion: number }>;
  error?: string;
};
export type GlyphStatus = 'missing' | 'imported' | 'processed' | 'approved' | 'error';

export type GlyphSource = {
  id: string;
  glyphName: string;
  character?: string;
  unicode?: number;
  sourceType: 'template' | 'individual-upload' | 'generated-component';
  sourceImagePath?: string;
  vectorPath?: string;
  variantGroup?: string;
  variantIndex?: number;
  transform: {
    scaleX: number;
    scaleY: number;
    translateX: number;
    translateY: number;
    rotation: number;
  };
  metrics: {
    advanceWidth: number;
    leftSideBearing: number;
    rightSideBearing: number;
  };
  processing: {
    threshold: number;
    invert: boolean;
    smoothing: number;
    despeckle: number;
    cropPadding: number;
    tracePreset?: 'preserve' | 'balanced' | 'smooth';
  };
  status: GlyphStatus;
  warnings?: string[];
  processedImagePath?: string;
  templatePlacement?: unknown;
  bounds?: { xMin: number; yMin: number; xMax: number; yMax: number; outlineWidth?: number; measurementVersion?: number };
};

export type KerningPair = { leftGlyph: string; rightGlyph: string; value: number; scope?: 'all-forms' | 'exact-forms' };

export type FontStyle = {
  id: string;
  name: string;
  fontWeight: number;
  fontStyle: 'normal' | 'italic' | 'oblique';
  glyphs: GlyphSource[];
  kerningPairs: KerningPair[];
  defaultSpaceWidth: number;
  defaultLeftBearing: number;
  defaultRightBearing: number;
  featureCode?: string;
};

export type FontProject = {
  schemaVersion: number;
  id: string;
  familyName: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
  unitsPerEm: number;
  ascender: number;
  descender: number;
  capHeight: number;
  xHeight: number;
  lineGap: number;
  styles: FontStyle[];
  templates: unknown[];
};
