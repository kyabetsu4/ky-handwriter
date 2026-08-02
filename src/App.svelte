<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './lib/components/Icon.svelte';
  import { createEmptyProject } from './lib/project';
  import { chooseFilledTemplates, chooseProjectFolder, compileFont, createProjectFolder, generateTemplate, importFilledTemplate, isTauri, loadProject, readProjectBinary, revealProjectFile, saveProject } from './lib/tauri';
  import type { FontProject, GlyphSource, ViewId } from './lib/types';

  let activeView: ViewId = $state('home');
  let project = $state<FontProject | null>(null);
  let lastBuiltProject = $state<FontProject | null>(null);
  let projectPath = $state('');
  type RecentProject = { path: string; name: string; openedAt: number };
  let recentProjects = $state<RecentProject[]>([]);

  function refreshPreviewDirty() {
    if (!project) {
      previewDirty = false;
      return;
    }
    previewDirty = !lastBuiltProject || JSON.stringify(project) !== JSON.stringify(lastBuiltProject);
  }
  let showCreate = $state(false);
  let showRename = $state(false);
  let renameFamilyName = $state('');
  let renamingProject = $state(false);
  type ProjectInfoKey = 'weight' | 'grid' | 'range' | 'folder';
  let projectInfo = $state<ProjectInfoKey | null>(null);
  const projectInfoContent: Record<ProjectInfoKey, { title: string; summary: string; kinds: Array<{ name: string; detail: string }> }> = {
    weight: { title: 'Font weight', summary: 'Weight describes how light or bold the letters appear. This project currently exports one Regular style.', kinds: [{ name: 'Light · 300', detail: 'Thin strokes and a delicate appearance.' }, { name: 'Regular · 400', detail: 'The standard choice for everyday text.' }, { name: 'Medium · 500', detail: 'Slightly stronger without looking bold.' }, { name: 'Bold · 700', detail: 'Heavy strokes for emphasis and headings.' }] },
    grid: { title: 'Font grid', summary: 'The font grid is the invisible coordinate system used to position and size every glyph. It does not control the font size chosen in other apps.', kinds: [{ name: '1000 units', detail: 'The common OpenType default and this project’s setting.' }, { name: '2048 units', detail: 'Common in TrueType fonts and allows finer integer coordinates.' }] },
    range: { title: 'Vertical range', summary: 'This sets how much room the font reserves above and below the baseline so tall letters, accents, and descenders are not clipped.', kinds: [{ name: 'Ascender', detail: 'Space above the baseline for letters such as b, h, and capitals.' }, { name: 'Descender', detail: 'Space below the baseline for letters such as g, p, and y.' }, { name: 'Line height', detail: 'Apps use these values together when laying out lines of text.' }] },
    folder: { title: 'Project location', summary: 'This is the folder containing the project data, imported handwriting, templates, and generated font files.', kinds: [{ name: 'sources', detail: 'Templates and the original imported glyph images.' }, { name: 'generated/regular', detail: 'The exported TTF, WOFF2, CSS, and validation files.' }, { name: 'project.json', detail: 'The saved settings and references for this font project.' }] },
  };
  let familyName = $state('My Handwriting');
  let message = $state('');
  let templatePreset = $state('a4-portrait');
  const characterSets = [
    { id: 'qwerty', name: 'Complete US QWERTY', description: 'Uppercase, lowercase, digits, and keyboard symbols', characters: "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM1234567890`~!@#$%^&*()-_=+[]{}\\|;:'\",.<>/?" },
    { id: 'letters', name: 'All letters', description: 'Uppercase and lowercase A-Z', characters: 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz' },
    { id: 'uppercase', name: 'Uppercase letters', description: 'A-Z', characters: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' },
    { id: 'lowercase', name: 'Lowercase letters', description: 'a-z', characters: 'abcdefghijklmnopqrstuvwxyz' },
    { id: 'numbers', name: 'Numbers', description: 'Digits 0-9', characters: '0123456789' },
    { id: 'symbols', name: 'Keyboard symbols', description: 'Common US keyboard punctuation', characters: "`~!@#$%^&*()-_=+[]{}\\|;:'\",.<>/?" },
  ];
  let templateCharacterSet = $state('qwerty');
  let templateCharacters = $derived(characterSets.find((set) => set.id === templateCharacterSet)?.characters ?? '');
  let templateVariants = $state(1);
  let templateReferenceLetters = $state(true);
  let generatingTemplate = $state(false);
  let templateResult = $state<{ outputs: string[]; pageCount: number } | null>(null);
  let importingTemplate = $state(false);
  let importResult = $state<{ imported: number; missing: number; pages: number; failed: number } | null>(null);
  let selectedGlyph = $state<GlyphSource | null>(null);
  let glyphEditPreviewText = $state('');
  let buildingGlyphDraft = $state(false);
  let glyphDraftReady = $state(false);
  let glyphHasDraftChanges = $state(false);
  let glyphDraftFontFace: FontFace | null = null;
  let glyphDraftRequest = 0;
  let glyphBaselineScaleX = $state(1);
  let glyphBaselineScaleY = $state(1);
  let glyphComparisonText = $state('minimum noon common sense');
  let glyphPageSearch = $state('');
  type GlyphFilter = 'all' | 'warnings' | 'missing' | 'imported';
  let glyphFilter = $state<GlyphFilter>('all');
  let glyphVariantCount = $derived(Math.max(1, ...(project?.styles[0]?.glyphs.map((glyph) => (glyph.variantIndex ?? 0) + 1) ?? [1])));
  let projectGlyphs = $derived(project?.styles[0]?.glyphs ?? []);
  let importedGlyphCount = $derived(projectGlyphs.filter((glyph) => glyph.status !== 'missing').length);
  let glyphFilterCounts = $derived({ warnings: projectGlyphs.filter((glyph) => Boolean(glyph.warnings?.length)).length, missing: projectGlyphs.filter((glyph) => glyph.status === 'missing').length, imported: projectGlyphs.filter((glyph) => glyph.status !== 'missing').length });
  let filteredGlyphPageGlyphs = $derived.by(() => {
    const query = glyphPageSearch.trim().toLocaleLowerCase();
    const filteredByStatus = projectGlyphs.filter((glyph) => glyphFilter === 'all' || (glyphFilter === 'warnings' && Boolean(glyph.warnings?.length)) || (glyphFilter === 'missing' && glyph.status === 'missing') || (glyphFilter === 'imported' && glyph.status !== 'missing'));
    if (!query) return filteredByStatus;
    const requestedCharacters = new Set([...query].filter((character) => !/\s/.test(character)));
    return filteredByStatus.filter((glyph) => {
      const character = String(glyph.character ?? '').toLocaleLowerCase();
      const form = `form ${(glyph.variantIndex ?? 0) + 1}`;
      if (query === 'missing') return glyph.status === 'missing';
      if (query === 'warning') return Boolean(glyph.warnings?.length);
      if (query.startsWith('form ') || query.startsWith('uni')) return `${glyph.glyphName} ${form}`.toLocaleLowerCase().includes(query);
      return requestedCharacters.has(character);
    });
  });
  let buildingPreview = $state(false);
  let previewReady = $state(false);
  let previewDirty = $state(false);
  let previewText = $state('Ideas grow with what you consume.\nInventiveness grows with what you create.');
  let previewSize = $state(54);
  let previewWarnings = $state<string[]>([]);
  let builtFontFiles = $state<{ ttf?: string; woff2?: string }>({});
  let previewFontFace: FontFace | null = null;
  let spacingGlyphId = $state('');
  let spacingGlyphSearch = $state('');
  let spacingGlyph = $derived.by((): GlyphSource | null => project?.styles[0]?.glyphs.find((glyph: GlyphSource) => glyph.id === spacingGlyphId) ?? null);
  let filteredSpacingGlyphs = $derived.by(() => {
    const query = spacingGlyphSearch.trim().toLocaleLowerCase();
    if (!query) return project?.styles[0]?.glyphs ?? [];
    const requestedCharacters = new Set([...query].filter((character) => !/\s/.test(character)));
    return (project?.styles[0]?.glyphs ?? []).filter((glyph) => {
      const character = String(glyph.character ?? '').toLocaleLowerCase();
      const form = `form ${(glyph.variantIndex ?? 0) + 1}`;
      if (query === 'missing') return glyph.status === 'missing';
      if (query === 'warning') return Boolean(glyph.warnings?.length);
      if (query.startsWith('form ') || query.startsWith('uni')) return `${glyph.glyphName} ${form}`.toLocaleLowerCase().includes(query);
      return requestedCharacters.has(character);
    });
  });
  let spacingNotice = $state('');
  let kerningLeft = $state('A');
  let kerningRight = $state('V');
  let kerningScope = $state<'all-forms' | 'exact-forms'>('all-forms');
  let kerningLeftForm = $state(0);
  let kerningRightForm = $state(0);
  let kerningValue = $state(-60);
  let kerningText = $state('AVATAR  To Ta Te Ty  WA We Wo');
  let kerningNotice = $state('');
  let kerningLeftForms = $derived(projectGlyphs.filter((glyph) => glyph.status !== 'missing' && glyph.character === kerningLeft).sort((a, b) => (a.variantIndex ?? 0) - (b.variantIndex ?? 0)));
  let kerningRightForms = $derived(projectGlyphs.filter((glyph) => glyph.status !== 'missing' && glyph.character === kerningRight).sort((a, b) => (a.variantIndex ?? 0) - (b.variantIndex ?? 0)));
  let selectedKerningLeftGlyph = $derived(kerningLeftForms.find((glyph) => (glyph.variantIndex ?? 0) === kerningLeftForm) ?? kerningLeftForms[0]);
  let selectedKerningRightGlyph = $derived(kerningRightForms.find((glyph) => (glyph.variantIndex ?? 0) === kerningRightForm) ?? kerningRightForms[0]);
  let currentKerningSavedValue = $derived.by(() => {
    const style = project?.styles[0];
    const left = kerningScope === 'exact-forms' ? selectedKerningLeftGlyph : kerningLeftForms.find((glyph) => (glyph.variantIndex ?? 0) === 0) ?? kerningLeftForms[0];
    const right = kerningScope === 'exact-forms' ? selectedKerningRightGlyph : kerningRightForms.find((glyph) => (glyph.variantIndex ?? 0) === 0) ?? kerningRightForms[0];
    return style?.kerningPairs.find((pair) => pair.leftGlyph === left?.glyphName && pair.rightGlyph === right?.glyphName && (pair.scope ?? 'all-forms') === kerningScope)?.value ?? null;
  });

  const nav: { id: ViewId; label: string }[] = [
    { id: 'home', label: 'Home' }, { id: 'glyphs', label: 'Glyphs' }, { id: 'spacing', label: 'Spacing' },
    { id: 'kerning', label: 'Kerning' }, { id: 'preview', label: 'Preview' }, { id: 'export', label: 'Export' },
  ];

  onMount(() => {
    try {
      recentProjects = JSON.parse(localStorage.getItem('handfont-recent-projects') || '[]');
    } catch {
      recentProjects = [];
    }
  });

  function rememberProject(path: string, name: string) {
    recentProjects = [{ path, name, openedAt: Date.now() }, ...recentProjects.filter((item) => item.path !== path)].slice(0, 8);
    localStorage.setItem('handfont-recent-projects', JSON.stringify(recentProjects));
  }

  $effect(() => {
    activeView;
    requestAnimationFrame(() => document.querySelector('main')?.scrollTo({ left: 0, top: 0 }));
  });

  async function beginProject() {
    message = '';
    const next = createEmptyProject(familyName);
    if (isTauri()) {
      const folder = await chooseProjectFolder();
      if (!folder) return;
      try {
        await createProjectFolder(folder, next);
        projectPath = folder;
        rememberProject(folder, next.familyName);
      } catch (error) {
        message = String(error);
        return;
      }
    } else {
      projectPath = 'Browser preview — desktop saving becomes available in Tauri';
    }
    project = next;
    lastBuiltProject = null;
    showCreate = false;
    activeView = 'home';
  }

  async function openProject() {
    message = '';
    if (!isTauri()) {
      message = 'Opening project folders is available in the desktop app.';
      return;
    }
    const folder = await chooseProjectFolder();
    if (!folder) return;
    await openProjectPath(folder);
  }

  async function openProjectPath(folder: string) {
    message = '';
    try {
      const loadedProject = await loadProject(folder);
      project = loadedProject;
      lastBuiltProject = null;
      projectPath = folder;
      rememberProject(folder, loadedProject.familyName);
      activeView = 'home';
      const existingGlyph = loadedProject.styles.some((style) => style.glyphs?.some((glyph) => glyph.status !== 'missing' && Boolean(glyph.sourceImagePath)));
      if (existingGlyph) {
        spacingGlyphId = loadedProject.styles[0]?.glyphs.find((glyph) => glyph.status !== 'missing')?.id ?? '';
        await buildFontPreview();
      }
    } catch (error) {
      message = String(error).replace(/^Error:\s*/, '');
      recentProjects = recentProjects.filter((item) => item.path !== folder);
      localStorage.setItem('handfont-recent-projects', JSON.stringify(recentProjects));
    }
  }

  async function selectRecentProject(event: Event) {
    const path = (event.currentTarget as HTMLSelectElement).value;
    if (path) await openProjectPath(path);
  }

  function openRenameProject() {
    if (!project) return;
    renameFamilyName = project.familyName;
    message = '';
    showRename = true;
  }

  async function renameProject() {
    if (!project || !projectPath || renamingProject) return;
    const nextName = renameFamilyName.trim();
    if (!nextName) {
      message = 'Enter a font family name.';
      return;
    }
    if (nextName === project.familyName) {
      showRename = false;
      return;
    }
    const previousName = project.familyName;
    renamingProject = true;
    message = '';
    project.familyName = nextName;
    try {
      if (isTauri()) await saveProject(projectPath, project);
      rememberProject(projectPath, nextName);
      refreshPreviewDirty();
      showRename = false;
    } catch (error) {
      project.familyName = previousName;
      message = String(error).replace(/^Error:\s*/, '');
    } finally {
      renamingProject = false;
    }
  }

  function closeProject() {
    selectedGlyph = null;
    project = null;
    lastBuiltProject = null;
    projectPath = '';
    activeView = 'home';
    spacingGlyphId = '';
    spacingGlyphSearch = '';
    glyphPageSearch = '';
    previewReady = false;
    previewDirty = false;
    previewWarnings = [];
    builtFontFiles = {};
    message = '';
    showRename = false;
  }

  function go(id: ViewId) {
    activeView = id;
    document.querySelector('main')?.scrollTo({ left: 0, top: 0 });
    selectedGlyph = null;
    message = '';
    if (id === 'spacing' && !spacingGlyphId) spacingGlyphId = project?.styles[0]?.glyphs.find((glyph) => glyph.status !== 'missing')?.id || project?.styles[0]?.glyphs[0]?.id || '';
  }

  function variantFeatures(variantIndex: number, contextual = false): string {
    if (contextual) return '"calt" 1';
    return variantIndex > 0 ? `"calt" 0, "ss${String(variantIndex).padStart(2, '0')}" 1` : '"calt" 0';
  }

  function inspectGlyph(glyph: GlyphSource) {
    selectedGlyph = glyph;
    glyphEditPreviewText = glyph.character ? `${glyph.character}${glyph.character} sample` : 'sample';
    glyphBaselineScaleX = glyph.transform.scaleX || 1;
    glyphBaselineScaleY = glyph.transform.scaleY || 1;
    glyphDraftReady = false;
    glyphHasDraftChanges = false;
  }

  async function buildGlyphDraftPreview() {
    if (!project || !projectPath || !selectedGlyph || !isTauri()) return;
    const request = ++glyphDraftRequest;
    buildingGlyphDraft = true;
    glyphDraftReady = false;
    try {
      await saveProject(projectPath, project);
      const outputDirectory = `${projectPath}\\generated\\.draft-preview`;
      const result = await compileFont(projectPath, outputDirectory);
      if (request !== glyphDraftRequest || !result.success || !result.outputs) return;
      const woff2 = result.outputs.find((path) => path.toLowerCase().endsWith('.woff2'));
      if (!woff2) return;
      const bytes = await readProjectBinary(projectPath, woff2);
      const buffer = new ArrayBuffer(bytes.byteLength);
      new Uint8Array(buffer).set(bytes);
      const face = new FontFace('HandfontDraftPreview', buffer);
      await face.load();
      if (glyphDraftFontFace) document.fonts.delete(glyphDraftFontFace);
      document.fonts.add(face);
      glyphDraftFontFace = face;
      glyphDraftReady = true;
    } catch {
      glyphDraftReady = false;
    } finally {
      if (request === glyphDraftRequest) buildingGlyphDraft = false;
    }
  }

  async function persistProject(notice = 'Saved') {
    if (!project || !projectPath) return;
    await saveProject(projectPath, project);
    spacingNotice = notice;
  }

  async function applySpacingDefaults() {
    const style = project?.styles[0];
    if (!style) return;
    for (const glyph of style.glyphs) {
      const inkWidth = Math.max(1, glyph.metrics.advanceWidth - glyph.metrics.leftSideBearing - glyph.metrics.rightSideBearing);
      glyph.metrics.leftSideBearing = style.defaultLeftBearing;
      glyph.metrics.rightSideBearing = style.defaultRightBearing;
      glyph.metrics.advanceWidth = inkWidth + style.defaultLeftBearing + style.defaultRightBearing;
    }
    await persistProject(`Applied defaults to ${style.glyphs.length} glyphs`);
    refreshPreviewDirty();
  }

  function inkWidth(glyph: GlyphSource): number {
    return Math.max(1, glyph.bounds?.outlineWidth ?? glyph.metrics.advanceWidth - glyph.metrics.leftSideBearing - glyph.metrics.rightSideBearing);
  }

  function setLeftGap(glyph: GlyphSource, value: number) {
    const width = inkWidth(glyph);
    glyph.metrics.leftSideBearing = value;
    glyph.metrics.advanceWidth = width + value + glyph.metrics.rightSideBearing;
    refreshPreviewDirty();
  }

  function setRightGap(glyph: GlyphSource, value: number) {
    const width = inkWidth(glyph);
    glyph.metrics.rightSideBearing = value;
    glyph.metrics.advanceWidth = width + glyph.metrics.leftSideBearing + value;
    refreshPreviewDirty();
  }

  async function resetGlyphSpacing(glyph: GlyphSource) {
    const style = project?.styles[0];
    if (!style || !project) return;
    const width = inkWidth(glyph);
    glyph.metrics.leftSideBearing = style.defaultLeftBearing;
    glyph.metrics.rightSideBearing = style.defaultRightBearing;
    glyph.metrics.advanceWidth = width + style.defaultLeftBearing + style.defaultRightBearing;
    await saveProject(projectPath, project);
    refreshPreviewDirty();
    spacingNotice = `${glyph.character} · Form ${(glyph.variantIndex ?? 0) + 1} reset to style defaults`;
  }

  async function offsetBearings(amount: number) {
    const style = project?.styles[0];
    if (!style) return;
    for (const glyph of style.glyphs) {
      glyph.metrics.leftSideBearing += amount;
      glyph.metrics.rightSideBearing += amount;
      glyph.metrics.advanceWidth += amount * 2;
    }
    await persistProject(`${amount > 0 ? 'Added' : 'Removed'} ${Math.abs(amount)} units on each side`);
    refreshPreviewDirty();
  }

  async function saveKerningPair() {
    const style = project?.styles[0];
    if (!style) return;
    const left = kerningScope === 'exact-forms' ? selectedKerningLeftGlyph : kerningLeftForms.find((glyph) => (glyph.variantIndex ?? 0) === 0) ?? kerningLeftForms[0];
    const right = kerningScope === 'exact-forms' ? selectedKerningRightGlyph : kerningRightForms.find((glyph) => (glyph.variantIndex ?? 0) === 0) ?? kerningRightForms[0];
    if (!left || !right) {
      message = 'Both characters must exist in the current glyph set.';
      return;
    }
    const existing = style.kerningPairs.find((pair) => pair.leftGlyph === left.glyphName && pair.rightGlyph === right.glyphName && (pair.scope ?? 'all-forms') === kerningScope);
    const wasExisting = Boolean(existing);
    if (existing) existing.value = kerningValue;
    else style.kerningPairs.push({ leftGlyph: left.glyphName, rightGlyph: right.glyphName, value: kerningValue, scope: kerningScope });
    await saveProject(projectPath, project!);
    refreshPreviewDirty();
    message = '';
    kerningNotice = `${kerningLeft}${kerningRight} ${kerningScope === 'all-forms' ? 'for all forms' : `Form ${(left.variantIndex ?? 0) + 1} + Form ${(right.variantIndex ?? 0) + 1}`} ${wasExisting ? 'updated' : 'saved'} at ${kerningValue}.`;
  }

  async function removeKerningPair(leftGlyph: string, rightGlyph: string, scope: 'all-forms' | 'exact-forms' = 'all-forms') {
    const style = project?.styles[0];
    if (!style) return;
    style.kerningPairs = style.kerningPairs.filter((pair) => pair.leftGlyph !== leftGlyph || pair.rightGlyph !== rightGlyph || (pair.scope ?? 'all-forms') !== scope);
    await saveProject(projectPath, project!);
    refreshPreviewDirty();
    kerningNotice = 'Saved pair removed. Build changes when you want to update the font.';
  }

  async function resetCurrentKerningPair() {
    const style = project?.styles[0];
    if (!style || !project) return;
    const left = kerningScope === 'exact-forms' ? selectedKerningLeftGlyph : kerningLeftForms.find((glyph) => (glyph.variantIndex ?? 0) === 0) ?? kerningLeftForms[0];
    const right = kerningScope === 'exact-forms' ? selectedKerningRightGlyph : kerningRightForms.find((glyph) => (glyph.variantIndex ?? 0) === 0) ?? kerningRightForms[0];
    if (!left || !right) return;
    style.kerningPairs = style.kerningPairs.filter((pair) => pair.leftGlyph !== left.glyphName || pair.rightGlyph !== right.glyphName || (pair.scope ?? 'all-forms') !== kerningScope);
    kerningValue = 0;
    await saveProject(projectPath, project);
    refreshPreviewDirty();
    kerningNotice = `${kerningLeft}${kerningRight} ${kerningScope === 'all-forms' ? 'all-forms adjustment' : `Form ${(left.variantIndex ?? 0) + 1} + Form ${(right.variantIndex ?? 0) + 1}`} reset to default spacing.`;
  }

  function editKerningPair(leftGlyph: string, rightGlyph: string, value: number, scope: 'all-forms' | 'exact-forms' = 'all-forms') {
    const style = project?.styles[0];
    const left = style?.glyphs.find((glyph) => glyph.glyphName === leftGlyph);
    const right = style?.glyphs.find((glyph) => glyph.glyphName === rightGlyph);
    kerningLeft = left?.character || leftGlyph;
    kerningRight = right?.character || rightGlyph;
    kerningScope = scope;
    kerningLeftForm = left?.variantIndex ?? 0;
    kerningRightForm = right?.variantIndex ?? 0;
    kerningValue = value;
    kerningNotice = `${kerningLeft}${kerningRight} loaded for editing.`;
  }

  async function setTracePreset(preset: 'preserve' | 'balanced' | 'smooth', applyToAll = false) {
    if (!project || !selectedGlyph || buildingPreview) return;
    const targets = applyToAll ? project.styles[0].glyphs.filter((glyph) => glyph.status !== 'missing') : [selectedGlyph];
    const settings = {
      preserve: { threshold: 200, smoothing: 0, despeckle: 2 },
      balanced: { threshold: 170, smoothing: 1, despeckle: 8 },
      smooth: { threshold: 150, smoothing: 2, despeckle: 14 },
    }[preset];
    for (const glyph of targets) {
      glyph.processing.tracePreset = preset;
      glyph.processing.threshold = settings.threshold;
      glyph.processing.smoothing = settings.smoothing;
      glyph.processing.despeckle = settings.despeckle;
      if (glyph.bounds) glyph.bounds.measurementVersion = 0;
    }
    await saveProject(projectPath, project);
    refreshPreviewDirty();
    glyphHasDraftChanges = true;
    await buildGlyphDraftPreview();
  }

  function setSelectedGlyphScale(percent: number) {
    if (!selectedGlyph) return;
    const scale = percent / 100;
    selectedGlyph.transform.scaleX = scale;
    selectedGlyph.transform.scaleY = scale;
    if (selectedGlyph.bounds) selectedGlyph.bounds.measurementVersion = 0;
    refreshPreviewDirty();
    glyphHasDraftChanges = true;
    glyphDraftReady = false;
  }

  async function saveSelectedGlyphScale() {
    if (!project || !selectedGlyph || buildingPreview) return;
    await saveProject(projectPath, project);
    refreshPreviewDirty();
    await buildGlyphDraftPreview();
  }

  async function resetSelectedGlyphScale() {
    setSelectedGlyphScale(100);
    await saveSelectedGlyphScale();
  }

  async function buildPendingPreview() {
    if (!project || buildingPreview) return;
    await saveProject(projectPath, project);
    await buildFontPreview();
  }

  async function discardPendingChanges() {
    if (!lastBuiltProject || !projectPath || buildingPreview) return;
    project = JSON.parse(JSON.stringify(lastBuiltProject)) as FontProject;
    await saveProject(projectPath, project);
    previewDirty = false;
    selectedGlyph = null;
    glyphDraftReady = false;
    glyphHasDraftChanges = false;
    spacingGlyphId = project.styles[0]?.glyphs.find((glyph) => glyph.status !== 'missing')?.id ?? '';
    spacingNotice = '';
    kerningNotice = '';
    message = '';
  }

  async function buildFontPreview() {
    if (!project || !projectPath || !isTauri()) return;
    buildingPreview = true;
    previewReady = false;
    message = '';
    try {
      await saveProject(projectPath, project);
      let result = await compileFont(projectPath);
      if (!result.success || !result.outputs) throw new Error(result.error || 'Font compilation failed');
      if (result.glyphBounds) {
        let boundsChanged = false;
        let metricsChanged = false;
        for (const glyph of project.styles[0].glyphs) {
          const measured = result.glyphBounds[glyph.glyphName];
          if (!measured) continue;
          if (glyph.bounds?.outlineWidth !== measured.outlineWidth) boundsChanged = true;
          glyph.bounds = measured;
          const correctedWidth = measured.outlineWidth + glyph.metrics.leftSideBearing + glyph.metrics.rightSideBearing;
          if (glyph.metrics.advanceWidth !== correctedWidth) {
            glyph.metrics.advanceWidth = correctedWidth;
            metricsChanged = true;
          }
        }
        if (boundsChanged || metricsChanged) await saveProject(projectPath, project);
        if (metricsChanged) {
          result = await compileFont(projectPath);
          if (!result.success || !result.outputs) throw new Error(result.error || 'Font recompilation failed after measuring glyph outlines');
        }
      }
      const woff2 = result.outputs.find((path) => path.toLowerCase().endsWith('.woff2'));
      const ttf = result.outputs.find((path) => path.toLowerCase().endsWith('.ttf'));
      if (!woff2) throw new Error('The compiler did not produce a WOFF2 preview font');
      builtFontFiles = { ttf, woff2 };
      const bytes = await readProjectBinary(projectPath, woff2);
      const fontBuffer = new ArrayBuffer(bytes.byteLength);
      new Uint8Array(fontBuffer).set(bytes);
      const face = new FontFace('HandfontPreview', fontBuffer);
      await face.load();
      if (previewFontFace) document.fonts.delete(previewFontFace);
      document.fonts.add(face);
      previewFontFace = face;
      previewWarnings = result.warnings || [];
      previewReady = true;
      previewDirty = false;
      lastBuiltProject = JSON.parse(JSON.stringify(project)) as FontProject;
    } catch (error) {
      message = String(error).replace(/^Error:\s*/, '');
    } finally {
      buildingPreview = false;
    }
  }

  async function showBuiltFontFile(path?: string) {
    if (!path) return;
    await revealProjectFile(path);
  }

  async function buildTemplate() {
    if (!project || !projectPath || !isTauri()) return;
    generatingTemplate = true;
    templateResult = null;
    message = '';
    try {
      const result = await generateTemplate(projectPath, templateCharacters, templatePreset, templateVariants, templateReferenceLetters);
      if (!result.success || !result.outputs || !result.templates) throw new Error(result.error || 'Template generation failed');
      project.templates = [...project.templates, ...result.templates];
      await saveProject(projectPath, project);
      templateResult = { outputs: result.outputs, pageCount: result.pageCount || 1 };
    } catch (error) {
      message = String(error).replace(/^Error:\s*/, '');
    } finally {
      generatingTemplate = false;
    }
  }

  async function reimportTemplatePages() {
    await loadCompletedTemplate('reimport');
  }

  async function loadCompletedTemplate(importMode: 'standard' | 'reimport' = 'standard') {
    if (!project || !projectPath || !isTauri()) return;
    message = '';
    importResult = null;
    const inputPaths = await chooseFilledTemplates();
    if (!inputPaths.length) return;
    importingTemplate = true;
    try {
      const style = project.styles.find((item) => item.id === 'regular');
      if (!style) throw new Error('The Regular style was not found');
      let imported = 0;
      let missing = 0;
      let failed = 0;
      const errors: string[] = [];
      for (const inputPath of inputPaths) {
        const result = await importFilledTemplate(projectPath, inputPath, importMode);
        if (!result.success || !result.glyphs) {
          failed += 1;
          errors.push(result.error || 'A template page could not be imported');
          continue;
        }
        imported += result.importedCount || 0;
        missing += result.missingCount || 0;
        for (const incoming of result.glyphs) {
          const index = style.glyphs.findIndex((existing) => existing.glyphName === incoming.glyphName);
          if (index >= 0) {
            const existing = style.glyphs[index];
            style.glyphs[index] = { ...incoming, transform: existing.transform, metrics: existing.metrics, processing: existing.processing, bounds: undefined };
          } else style.glyphs.push(incoming);
        }
      }
      if (failed === inputPaths.length) throw new Error(errors[0] || 'None of the selected pages could be imported');
      await saveProject(projectPath, project);
      refreshPreviewDirty();
      if (selectedGlyph) selectedGlyph = style.glyphs.find((glyph) => glyph.glyphName === selectedGlyph?.glyphName) ?? selectedGlyph;
      importResult = { imported, missing, pages: inputPaths.length - failed, failed };
      if (errors.length) message = `${failed} page${failed === 1 ? '' : 's'} failed: ${errors.join('; ')}`;
    } catch (error) {
      message = String(error).replace(/^Error:\s*/, '');
    } finally {
      importingTemplate = false;
    }
  }
</script>

<div class="shell">
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">ky</span><span>ky.handwriter</span></div>
    <nav aria-label="Main navigation">
      {#each nav as item}
        <button class:active={activeView === item.id} onclick={() => go(item.id)} disabled={!project && item.id !== 'home'}>
          <Icon name={item.id} size={19} /><span>{item.label}</span>
        </button>
      {/each}
    </nav>
    {#if project}
      <div class="sidebar-project-actions">
        <button onclick={openRenameProject}><span>Rename font</span></button>
        <button onclick={closeProject}><span>Close project</span></button>
      </div>
    {/if}
    {#if project && importedGlyphCount}
      <section class="pending-build" aria-live="polite">
        {#if previewDirty}<div class="pending-build-status"><strong>Changes not built</strong>{#if lastBuiltProject}<button class="pending-dismiss" aria-label="Discard changes since the last build" title="Discard changes since the last build" onclick={discardPendingChanges}>×</button>{/if}</div>{/if}
        <button onclick={buildPendingPreview} disabled={buildingPreview}>{buildingPreview ? 'Building…' : previewDirty ? 'Build changes' : previewReady ? 'Rebuild font' : 'Build font'}</button>
      </section>
    {/if}
  </aside>

  <main>
    {#if activeView === 'home' && !project}
      <section class="home home-launcher">
        <h1>ky.handwriter</h1>
        <p class="lede">Create a new font or open a project to continue.</p>
        <div class="actions">
          <button class="primary" onclick={() => showCreate = true}><Icon name="plus" size={18} /> Create a new font</button>
          <button class="secondary" onclick={openProject}><Icon name="folder" size={18} /> Open project folder</button>
        </div>
        {#if recentProjects.length}
          <label class="recent-project-picker"><span>Recent projects</span><select aria-label="Open a recent project" onchange={selectRecentProject}><option value="">Choose a project…</option>{#each recentProjects as recent}<option value={recent.path}>{recent.name} — {recent.path}</option>{/each}</select></label>
        {/if}
        {#if message}<p class="home-error">{message}</p>{/if}
      </section>
    {:else if project}
      <section class="workspace" class:spacing-workspace={activeView === 'spacing'}>
        {#if activeView === 'home'}
          <div class="home-dashboard">
            <section class="home-template-section" id="home-template-tools">
              <div class="home-section-label"><h2>Create or import handwriting sheets</h2></div>
              <div class="template-layout">
                <div class="template-form">
                  <label>Character set<select bind:value={templateCharacterSet}>{#each characterSets as set}<option value={set.id}>{set.name}</option>{/each}</select></label>
                  <label>Page format<select bind:value={templatePreset}><option value="a4-portrait">A4 portrait - 300 DPI</option><option value="letter-portrait">US Letter portrait - 300 DPI</option></select></label>
                  <label>Forms per character<select bind:value={templateVariants}><option value={1}>1 form</option><option value={2}>2 forms</option><option value={3}>3 forms</option><option value={4}>4 forms</option></select></label>
                  <label class="check-row"><input type="checkbox" bind:checked={templateReferenceLetters} /><span><strong>Show reference letters</strong></span></label>
                  <div class="template-note"><strong>{templateCharacters.length * templateVariants} writing cells</strong><span>{Math.ceil(templateCharacters.length * templateVariants / 28)} page{Math.ceil(templateCharacters.length * templateVariants / 28) === 1 ? '' : 's'} · 28 per page</span></div>
                  <button class="primary template-generate" onclick={buildTemplate} disabled={generatingTemplate}>{generatingTemplate ? 'Generating…' : 'Generate PNG + PDF'} <Icon name="arrow" size={17}/></button>
                  {#if templateResult}<div class="template-success"><strong>Template ready</strong><span>{templateResult.pageCount} page{templateResult.pageCount === 1 ? '' : 's'} saved in <code>sources/templates</code>.</span></div>{/if}
                  <div class="import-divider"><span>Completed your sheet?</span></div>
                  <button class="secondary template-import" onclick={() => loadCompletedTemplate()} disabled={importingTemplate}><Icon name="folder" size={17}/>{importingTemplate ? 'Reading pages…' : 'Load completed templates'}</button>
                  {#if message}<p class="error">{message}</p>{/if}
                  {#if importResult}<div class="import-success"><strong>{importResult.pages} page{importResult.pages === 1 ? '' : 's'} imported</strong><span>{importResult.imported} glyphs found · {importResult.missing} blank{importResult.failed ? ` · ${importResult.failed} failed` : ''}</span><button onclick={() => go('glyphs')}>Review glyphs <Icon name="arrow" size={15}/></button></div>{/if}
                </div>
                <div class="sheet-preview">
                  <div class="sheet-head"><div><strong>{project.familyName}</strong><small>HANDWRITING TEMPLATE / REGULAR</small></div><div class="fake-qr">⌗</div></div>
                  <p>Write in black. Keep each character inside its box.</p>
                  <div class="sheet-cells">{#each Array.from({length: 12}) as _, index}<div><b>{templateCharacters[index] || ''}</b>{#if templateReferenceLetters}<em>{templateCharacters[index] || ''}</em>{/if}<i></i><i></i><i class="baseline"></i></div>{/each}</div>
                  <span class="marker tl"></span><span class="marker tr"></span><span class="marker bl"></span><span class="marker br"></span>
                </div>
              </div>
            </section>
          </div>
        {:else if activeView === 'project'}
          <div class="metric-grid">
            <article><small>Style</small><strong>Regular</strong><span>400 · Normal</span></article>
            <article><small>Character set</small><strong>Uppercase A–Z</strong><span>0 of 26 imported</span></article>
            <article><small>Units per em</small><strong>{project.unitsPerEm}</strong><span>Ascender {project.ascender} · Descender {project.descender}</span></article>
          </div>
          <div class="panel"><div><span class="overline">FIRST MILESTONE</span><h2>Build your uppercase alphabet</h2><p>Import one PNG for each letter, tune the outlines and spacing, then compile your first working font.</p></div><button class="primary" onclick={() => go('glyphs')}>Continue to glyphs <Icon name="arrow" size={17}/></button></div>
        {:else if activeView === 'template'}
          <div class="template-layout">
            <div class="template-form">
              <label>Character set<select bind:value={templateCharacterSet}>{#each characterSets as set}<option value={set.id}>{set.name}</option>{/each}</select></label>
              <label>Page format<select bind:value={templatePreset}><option value="a4-portrait">A4 portrait - 300 DPI</option><option value="letter-portrait">US Letter portrait - 300 DPI</option></select></label>
              <label>Forms per character<select bind:value={templateVariants}><option value={1}>1 form</option><option value={2}>2 forms</option><option value={3}>3 forms</option><option value={4}>4 forms</option></select></label>
              <label class="check-row"><input type="checkbox" bind:checked={templateReferenceLetters} /><span><strong>Show reference letters</strong></span></label>
              <div class="template-note"><strong>{templateCharacters.length * templateVariants} writing cells</strong><span>{Math.ceil(templateCharacters.length * templateVariants / 28)} page{Math.ceil(templateCharacters.length * templateVariants / 28) === 1 ? '' : 's'} · 28 per page</span></div>
              <button class="primary template-generate" onclick={buildTemplate} disabled={generatingTemplate}>{generatingTemplate ? 'Generating…' : 'Generate PNG + PDF'} <Icon name="arrow" size={17}/></button>
              {#if templateResult}<div class="template-success"><strong>Template ready</strong><span>{templateResult.pageCount} page{templateResult.pageCount === 1 ? '' : 's'} saved in your project’s <code>sources/templates</code> folder.</span></div>{/if}
              <div class="import-divider"><span>Completed your sheet?</span></div>
              <button class="secondary template-import" onclick={() => loadCompletedTemplate()} disabled={importingTemplate}><Icon name="folder" size={17}/>{importingTemplate ? 'Reading template pages…' : 'Load completed templates'}</button>
              {#if message}<p class="error">{message}</p>{/if}
              {#if importResult}<div class="import-success"><strong>{importResult.pages} page{importResult.pages === 1 ? '' : 's'} imported</strong><span>{importResult.imported} glyphs found · {importResult.missing} blank{importResult.failed ? ` · ${importResult.failed} failed` : ''}</span><button onclick={() => activeView = 'glyphs'}>Review glyphs <Icon name="arrow" size={15}/></button></div>{/if}
            </div>
            <div class="sheet-preview">
              <div class="sheet-head"><div><strong>{project.familyName}</strong><small>HANDWRITING TEMPLATE / REGULAR</small></div><div class="fake-qr">▦</div></div>
              <p>Write in black. Keep each character inside its box.</p>
              <div class="sheet-cells">{#each Array.from({length: 12}) as _, index}<div><b>{templateCharacters[index] || ''}</b>{#if templateReferenceLetters}<em>{templateCharacters[index] || ''}</em>{/if}<i></i><i></i><i class="baseline"></i></div>{/each}</div>
              <span class="marker tl"></span><span class="marker tr"></span><span class="marker bl"></span><span class="marker br"></span>
            </div>
          </div>
        {:else if activeView === 'glyphs'}
          <div class="view-banner"><strong>Individual Glyphs <button type="button" class="info-tip" aria-label="Review each imported character form, compare variants, and open a glyph to refine it." data-tip="Review each imported character form, compare variants, and open a glyph to refine it.">i</button></strong></div>
          <section class="variant-comparison">
            <div class="variant-compact-bar"><label class="comparison-text-field"><span>Comparison text</span><input bind:value={glyphComparisonText} spellcheck="false" placeholder="Type text to compare forms" /></label></div>
            <div class="comparison-rows">
              <div><strong>Contextual mix</strong><p style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-feature-settings={variantFeatures(0, true)}>{glyphComparisonText}</p></div>
              {#each Array.from({ length: glyphVariantCount }) as _, variantIndex}
                <div><strong>Form {variantIndex + 1}</strong><p style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-feature-settings={variantFeatures(variantIndex)}>{glyphComparisonText}</p></div>
              {/each}
            </div>
          </section>
          <div class="glyph-sticky-tools">
            <label class="glyph-page-search"><Icon name="search" size={17}/><input bind:value={glyphPageSearch} placeholder="Search glyphs — try ab1, form 2, missing…" aria-label="Search glyphs" /><span>{filteredGlyphPageGlyphs.length} / {projectGlyphs.length}</span>{#if glyphPageSearch}<button aria-label="Clear glyph search" onclick={() => glyphPageSearch = ''}>×</button>{/if}</label>
            <div class="glyph-filter-row">
              <div class="glyph-filters" aria-label="Filter glyphs">{#each [{ id: 'all', label: 'All', count: projectGlyphs.length }, { id: 'warnings', label: 'Has warnings', count: glyphFilterCounts.warnings }, { id: 'missing', label: 'Missing', count: glyphFilterCounts.missing }, { id: 'imported', label: 'Imported', count: glyphFilterCounts.imported }] as filter}<button class:active={glyphFilter === filter.id} onclick={() => glyphFilter = filter.id as GlyphFilter}>{filter.label}<span>{filter.count}</span></button>{/each}</div>
              <button class="reimport-page-button" onclick={reimportTemplatePages} disabled={importingTemplate}><Icon name="folder" size={17}/>{importingTemplate ? 'Re-importing page…' : 'Re-import template page'}</button>
            </div>
          </div>
          {#if message}<p class="preview-error">{message}</p>{/if}
          <div class="glyph-grid variant-grid">
            {#each filteredGlyphPageGlyphs as glyph}
              <button class:has-warning={glyph.warnings?.length} class:selected={selectedGlyph?.id === glyph.id} onclick={() => inspectGlyph(glyph)}><span style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-feature-settings={variantFeatures(glyph.variantIndex ?? 0)}>{glyph.character}</span><b>{glyph.variantIndex ? `Form ${glyph.variantIndex + 1}` : 'Form 1'}</b><small>{glyph.status}{glyph.warnings?.length ? ` · ${glyph.warnings.length} warning` : ''}</small></button>
            {/each}
          </div>
          {#if !filteredGlyphPageGlyphs.length}<p class="glyph-search-empty">No matching glyphs</p>{/if}
        {:else if activeView === 'spacing'}
          <div class="spacing-layout">
            <aside class="spacing-list">
              <div class="spacing-list-head"><strong>Glyphs</strong><span>{spacingGlyphSearch ? `${filteredSpacingGlyphs.length} / ` : ''}{project.styles[0].glyphs.length}</span></div>
              <label class="spacing-search"><Icon name="search" size={15}/><input bind:value={spacingGlyphSearch} placeholder="Search glyphs" aria-label="Search glyphs" />{#if spacingGlyphSearch}<button aria-label="Clear glyph search" onclick={() => spacingGlyphSearch = ''}>×</button>{/if}</label>
              <div class="spacing-glyphs">{#each filteredSpacingGlyphs as glyph}<button class:active={spacingGlyphId === glyph.id} class:missing={glyph.status === 'missing'} title={`${glyph.character} · Form ${(glyph.variantIndex ?? 0) + 1}`} onclick={() => spacingGlyphId = glyph.id}><span>{glyph.character}</span><small>F{(glyph.variantIndex ?? 0) + 1}</small></button>{/each}</div>
              {#if !filteredSpacingGlyphs.length}<p class="spacing-search-empty">No matching glyphs</p>{/if}
            </aside>
            <div class="spacing-editor">
              <div class="spacing-explainer"><strong>Character spacing <button type="button" class="info-tip" aria-label="Each glyph sits inside an invisible box. Its side gaps prevent adjacent letters from touching." data-tip="Each glyph sits inside an invisible box. Its side gaps prevent adjacent letters from touching.">i</button></strong></div>
              {#if spacingGlyph}
                <div class="spacing-selection"><div class="spacing-selection-title" title={spacingGlyph.glyphName}><strong>{spacingGlyph.character}</strong><span>Form {(spacingGlyph.variantIndex ?? 0) + 1}</span></div><button onclick={() => resetGlyphSpacing(spacingGlyph!)}>Reset this form to defaults</button></div>
                <div class="metric-stage">
                  <div class="metric-box" style:width={`${Math.max(35, Math.min(92, spacingGlyph.metrics.advanceWidth / 9))}%`} style:grid-template-columns={`${Math.max(0, spacingGlyph.metrics.leftSideBearing)}fr ${inkWidth(spacingGlyph)}fr ${Math.max(0, spacingGlyph.metrics.rightSideBearing)}fr`}>
                    <div class="gap-zone left-zone"><span>{spacingGlyph.metrics.leftSideBearing}</span></div>
                    <div class="ink-zone"><svg class="metric-glyph" aria-label={spacingGlyph.character} overflow="visible"><text x="50%" y="100%" style:font-family={previewReady ? 'HandfontPreview' : 'Segoe UI, sans-serif'} style:font-feature-settings={variantFeatures(spacingGlyph.variantIndex ?? 0)}>{spacingGlyph.character}</text></svg><small>drawn letter</small></div>
                    <div class="gap-zone right-zone"><span>{spacingGlyph.metrics.rightSideBearing}</span></div>
                  </div>
                </div>
                <div class="metric-fields">
                  <label><span>Left gap <button type="button" class="info-tip" aria-label="Moves the drawn glyph to the right inside its character box." data-tip="Moves the drawn glyph to the right inside its character box.">i</button></span><input type="number" value={spacingGlyph.metrics.leftSideBearing} oninput={(event) => setLeftGap(spacingGlyph!, Number(event.currentTarget.value))} /></label>
                  <label class="calculated-width"><span>Total character width <button type="button" class="info-tip" aria-label="Calculated from the drawn glyph width plus its left and right gaps." data-tip="Calculated from the drawn glyph width plus its left and right gaps.">i</button></span><output>{spacingGlyph.metrics.advanceWidth}</output></label>
                  <label><span>Right gap <button type="button" class="info-tip" aria-label="Controls where the following character begins." data-tip="Controls where the following character begins.">i</button></span><input type="number" value={spacingGlyph.metrics.rightSideBearing} oninput={(event) => setRightGap(spacingGlyph!, Number(event.currentTarget.value))} /></label>
                </div>
                <div class="context-preview" style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'}>HH{spacingGlyph.character}HH &nbsp; nn{spacingGlyph.character}nn</div>
              {:else}<div class="spacing-empty">Import a glyph to edit its spacing.</div>{/if}
              {#if spacingNotice}<p class="spacing-notice">{spacingNotice}</p>{/if}
            </div>
            <aside class="spacing-defaults">
              <span class="overline">STYLE DEFAULTS <button type="button" class="info-tip" aria-label="Starting values for newly imported glyphs. Apply them to every glyph using the button below." data-tip="Starting values for newly imported glyphs. Apply them to every glyph using the button below.">i</button></span>
              <label>Default left gap<input type="number" bind:value={project.styles[0].defaultLeftBearing}/></label>
              <label>Default right gap<input type="number" bind:value={project.styles[0].defaultRightBearing}/></label>
              <label>Width of a space<input type="number" min="1" bind:value={project.styles[0].defaultSpaceWidth}/></label>
              <button onclick={applySpacingDefaults}>Use these gaps for every letter</button>
              <div class="bulk-buttons"><button onclick={() => offsetBearings(-5)}>−5 both sides</button><button onclick={() => offsetBearings(5)}>+5 both sides</button></div>
            </aside>
          </div>
        {:else if activeView === 'kerning'}
          <div class="view-banner"><strong>Character Kerning <button type="button" class="info-tip" aria-label="Adjust the space between specific letter pairs without changing each letter's general spacing." data-tip="Adjust the space between specific letter pairs without changing each letter's general spacing.">i</button></strong></div>
          <div class="kerning-layout">
            <div class="kerning-main">
              <div class="kerning-workflow"><div><b>1</b><span><strong>Choose two letters</strong><small>The exact adjacent combination</small></span></div><div><b>2</b><span><strong>Adjust the distance</strong><small>Negative is tighter; positive is wider</small></span></div><div><b>3</b><span><strong>Save the combination</strong><small>Stores an exception for this pair only</small></span></div></div>
              <div class="kerning-preview" class:compiled={previewReady} style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'}>{kerningText}</div>
              <label class="kerning-text-label">Preview text<input bind:value={kerningText}/></label>
              <div class="pair-editor">
                <div class="pair-editor-topbar">
                  <div class="pair-editor-head"><span>Pair adjustment</span><div class="pair-editor-title"><strong>{kerningLeft || '–'} + {kerningRight || '–'}</strong><em class="pair-editor-status" class:saved={currentKerningSavedValue === kerningValue} class:changed={currentKerningSavedValue !== null && currentKerningSavedValue !== kerningValue}>{currentKerningSavedValue === null ? 'New pair' : currentKerningSavedValue === kerningValue ? 'Saved' : 'Unsaved change'}</em></div></div>
                  <div class="pair-editor-options">
                    {#if kerningScope === 'exact-forms'}<div class="kerning-form-pickers"><label><select aria-label={`${kerningLeft || 'First letter'} form`} bind:value={kerningLeftForm}>{#each kerningLeftForms as glyph}<option value={glyph.variantIndex ?? 0}>Form {(glyph.variantIndex ?? 0) + 1}</option>{/each}</select></label><span>+</span><label><select aria-label={`${kerningRight || 'Second letter'} form`} bind:value={kerningRightForm}>{#each kerningRightForms as glyph}<option value={glyph.variantIndex ?? 0}>Form {(glyph.variantIndex ?? 0) + 1}</option>{/each}</select></label></div>{/if}
                    <div class="kerning-scope"><button class:active={kerningScope === 'all-forms'} onclick={() => { kerningScope = 'all-forms'; kerningNotice = ''; }}>All forms</button><button class:active={kerningScope === 'exact-forms'} onclick={() => { kerningScope = 'exact-forms'; kerningNotice = ''; }}>Exact forms</button></div>
                  </div>
                </div>
                <div class="live-kern-pair" style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'}><span style:font-feature-settings={kerningScope === 'exact-forms' ? variantFeatures(selectedKerningLeftGlyph?.variantIndex ?? 0) : variantFeatures(0)}>{kerningLeft || 'A'}</span><span style:margin-left={`${kerningValue * 0.1}px`} style:font-feature-settings={kerningScope === 'exact-forms' ? variantFeatures(selectedKerningRightGlyph?.variantIndex ?? 0) : variantFeatures(0)}>{kerningRight || 'V'}</span></div>
                <div class="pair-characters"><label>First letter<input maxlength="1" bind:value={kerningLeft} oninput={() => kerningNotice = ''}/></label><span>{kerningValue} units</span><label>Second letter<input maxlength="1" bind:value={kerningRight} oninput={() => kerningNotice = ''}/></label></div>
                <label class="kern-slider"><span>Tighter</span><input aria-label="Pair distance" type="range" min="-250" max="250" step="1" bind:value={kerningValue} oninput={() => kerningNotice = ''}/><span>Wider</span></label>
                <div class="kern-number"><label>Exact adjustment <input type="number" min="-500" max="500" bind:value={kerningValue} oninput={() => kerningNotice = ''}/></label><button class="secondary kern-reset" onclick={resetCurrentKerningPair} disabled={currentKerningSavedValue === null && kerningValue === 0}>Reset this pair</button><button class="primary" onclick={saveKerningPair}>Save {kerningLeft}{kerningRight} spacing</button></div>
                {#if kerningNotice}<p class="kerning-notice">{kerningNotice}</p>{/if}
                {#if message}<p class="preview-error">{message}</p>{/if}
              </div>
            </div>
            <aside class="pair-list"><div class="pair-list-head"><strong>Saved pair adjustments</strong><span>{project.styles[0].kerningPairs.length}</span></div>{#if project.styles[0].kerningPairs.length}{#each project.styles[0].kerningPairs as pair}<div class="pair-row"><button onclick={() => editKerningPair(pair.leftGlyph, pair.rightGlyph, pair.value, pair.scope ?? 'all-forms')}><div><strong>{pair.leftGlyph}{pair.rightGlyph}</strong><small>{(pair.scope ?? 'all-forms') === 'exact-forms' ? 'Exact forms' : 'All forms'}</small></div><span>{pair.value}</span></button><button class="pair-remove" aria-label={`Remove ${pair.leftGlyph} ${pair.rightGlyph}`} onclick={() => removeKerningPair(pair.leftGlyph, pair.rightGlyph, pair.scope ?? 'all-forms')}>×</button></div>{/each}{:else}<p>No saved pairs yet. Try combinations such as AV, To, or WA.</p>{/if}</aside>
          </div>
        {:else if activeView === 'preview'}
          <div class="view-banner"><strong>Check out the font <button type="button" class="info-tip" aria-label="Try your font with different text and sizes before exporting it." data-tip="Try your font with different text and sizes before exporting it.">i</button></strong></div>
          <div class="preview-tools">
            <div class="preview-presets"><button onclick={() => previewText = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789'}>Character set</button><button onclick={() => previewText = 'The quick brown fox jumps over the lazy dog.'}>Pangram</button><button onclick={() => previewText = 'AVATAR · To Ta Te Ty · WA We Wo'}>Kerning</button></div>
            <div class="preview-tool-actions"><label>Size <input type="range" min="20" max="110" bind:value={previewSize}/><span>{previewSize}px</span></label></div>
          </div>
          {#if message}<p class="preview-error">{message}</p>{/if}
          <textarea class:compiled={previewReady} class="preview-copy" bind:value={previewText} style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-size={`${previewSize}px`} spellcheck="false"></textarea>
          {#if previewWarnings.length}<div class="preview-foot"><span>{previewWarnings.length} compiler warning{previewWarnings.length === 1 ? '' : 's'}</span></div>{/if}
        {:else if activeView === 'export'}
          <section class="export-page">
            <div class="export-card">
              <div><h2>{previewDirty ? 'Build your latest changes' : previewReady ? 'Your font is ready' : 'Build your font'}</h2><p>{previewDirty ? 'Your saved edits are not included in the current files yet.' : 'Use TTF in desktop apps and WOFF2 on websites.'}</p></div>
              {#if previewReady && builtFontFiles.ttf && builtFontFiles.woff2}
                <div class="export-files"><button onclick={() => showBuiltFontFile(builtFontFiles.ttf)}><Icon name="export" size={21}/><span><strong>Desktop font</strong><small>TrueType · .ttf</small></span><b>Show file</b></button><button onclick={() => showBuiltFontFile(builtFontFiles.woff2)}><Icon name="export" size={21}/><span><strong>Web font</strong><small>WOFF2 · .woff2</small></span><b>Show file</b></button></div>
              {/if}
              {#if message}<p class="preview-error">{message}</p>{/if}
            </div>
          </section>
        {:else}
          <div class="empty-state"><div class="mini glyph-mini">Aa</div><h2>{nav.find((n) => n.id === activeView)?.label} tools</h2><p>This workspace is staged for the next milestone after glyph import and compilation are connected.</p></div>
        {/if}
      </section>
    {/if}
  </main>
</div>

{#if buildingPreview}
  <div class="build-blocker" role="alert" aria-live="assertive" aria-busy="true">
    <div class="build-dialog">
      <div class="build-copy">
        <strong>Building your font</strong>
      </div>
    </div>
  </div>
{/if}

{#if showCreate}
  <div class="modal-backdrop" role="presentation" onclick={(e) => e.currentTarget === e.target && (showCreate = false)}>
    <form class="modal" onsubmit={(e) => { e.preventDefault(); beginProject(); }}>
      <span class="overline">NEW LOCAL PROJECT</span><h2>Name your font family</h2><p>You can change this later. The project will be stored as a normal folder you control.</p>
      <label>Family name<input bind:value={familyName} /></label>
      {#if message}<p class="error">{message}</p>{/if}
      <div class="modal-actions"><button type="button" class="text-button" onclick={() => showCreate = false}>Cancel</button><button class="primary" type="submit">Choose folder <Icon name="arrow" size={17}/></button></div>
    </form>
  </div>
{/if}

{#if showRename}
  <div class="modal-backdrop" role="presentation" onclick={(event) => event.currentTarget === event.target && !renamingProject && (showRename = false)}>
    <form class="modal" aria-labelledby="rename-font-title" onsubmit={(event) => { event.preventDefault(); renameProject(); }}>
      <span class="overline">PROJECT SETTINGS</span><h2 id="rename-font-title">Rename your font</h2><p>This changes the font family name stored in the project. Build the font again to update exported files.</p>
      <label>Family name<input bind:value={renameFamilyName} disabled={renamingProject} /></label>
      {#if message}<p class="error">{message}</p>{/if}
      <div class="modal-actions"><button type="button" class="text-button" disabled={renamingProject} onclick={() => showRename = false}>Cancel</button><button class="primary" type="submit" disabled={renamingProject}>{renamingProject ? 'Saving…' : 'Save name'}</button></div>
    </form>
  </div>
{/if}

{#if projectInfo}
  <div class="modal-backdrop" role="presentation" onclick={(event) => event.currentTarget === event.target && (projectInfo = null)}>
    <div class="modal project-info-modal" role="dialog" aria-modal="true" aria-labelledby="project-info-title">
      <button class="inspector-close" aria-label="Close explanation" onclick={() => projectInfo = null}>×</button>
      <h2 id="project-info-title">{projectInfoContent[projectInfo].title}</h2>
      <p>{projectInfoContent[projectInfo].summary}</p>
      <div class="project-info-kinds" class:weight-options={projectInfo === 'weight'} class:grid-options={projectInfo === 'grid'} class:range-options={projectInfo === 'range'} class:folder-options={projectInfo === 'folder'}>
        {#each projectInfoContent[projectInfo].kinds as kind, index}
          <article>
            {#if projectInfo === 'weight'}<div class="weight-sample" style:font-weight={[300, 400, 500, 700][index]}>Aa</div>
            {:else if projectInfo === 'grid'}<div class="grid-sample"><i></i><i></i><b>{kind.name.split(' ')[0]}</b></div>
            {:else if projectInfo === 'range'}<div class="range-sample" class:below={index === 1}><span>{index === 1 ? 'g' : index === 2 ? 'Ag' : 'H'}</span><i></i></div>
            {:else}<div class="folder-sample"><Icon name="folder" size={19}/></div>{/if}
            <div><strong>{kind.name}{(projectInfo === 'weight' && index === 1) || (projectInfo === 'grid' && index === 0) ? ' · Current' : ''}</strong><span>{kind.detail}</span></div>
          </article>
        {/each}
      </div>
    </div>
  </div>
{/if}

{#if selectedGlyph}
  <div class="inspector-backdrop" role="presentation" onclick={(event) => event.currentTarget === event.target && (selectedGlyph = null)}>
    <aside class="glyph-inspector">
      <button class="inspector-close" aria-label="Close glyph details" onclick={() => selectedGlyph = null}>×</button>
      <span class="overline">GLYPH DETAILS</span>
      <div class="glyph-inspector-top">
        <div class="glyph-inspector-identity"><div class="inspector-character" style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-feature-settings={variantFeatures(selectedGlyph.variantIndex ?? 0)}>{selectedGlyph.character}</div><h2>{selectedGlyph.glyphName}</h2><p class="inspector-status">Form {(selectedGlyph.variantIndex ?? 0) + 1} · {selectedGlyph.status} · {selectedGlyph.sourceType}</p></div>
        <section class="glyph-change-preview">
          <label>Test word<input bind:value={glyphEditPreviewText} spellcheck="false" placeholder="Type a word" /></label>
          <div class="glyph-preview-compare">
            <article><small>Before</small><p style:font-family={previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-feature-settings={variantFeatures(selectedGlyph.variantIndex ?? 0)}>{glyphEditPreviewText}</p></article>
            <article class="after"><small>After {#if buildingGlyphDraft}<span>Updating…</span>{/if}</small><p style:font-family={glyphDraftReady ? 'HandfontDraftPreview' : previewReady ? 'HandfontPreview' : 'Georgia, serif'} style:font-feature-settings={variantFeatures(selectedGlyph.variantIndex ?? 0)}>{#if !glyphHasDraftChanges}{glyphEditPreviewText}{:else if glyphDraftReady}{glyphEditPreviewText}{:else}{#each [...glyphEditPreviewText] as character}<span class:edited-character={character === selectedGlyph.character} style:transform={character === selectedGlyph.character ? `scale(${(selectedGlyph.transform.scaleX || 1) / glyphBaselineScaleX}, ${(selectedGlyph.transform.scaleY || 1) / glyphBaselineScaleY})` : undefined}>{character}</span>{/each}{/if}</p></article>
          </div>
        </section>
      </div>
      {#if selectedGlyph.warnings?.length}
        <section class="warning-detail"><h3>Needs attention</h3>{#each selectedGlyph.warnings as warning}<p>{warning}</p>{/each}</section>
      {:else}<section class="clear-detail"><h3>No warnings</h3><p>This glyph passed the initial ink and boundary checks.</p></section>{/if}
      <section class="glyph-size-detail"><div><h3>Glyph size</h3><output>{Math.round((selectedGlyph.transform.scaleY || 1) * 100)}%</output></div><input type="range" min="60" max="180" step="1" value={Math.round((selectedGlyph.transform.scaleY || 1) * 100)} oninput={(event) => setSelectedGlyphScale(Number(event.currentTarget.value))} onchange={saveSelectedGlyphScale} disabled={buildingPreview}/><div class="size-scale"><span>Smaller</span><i></i><span>Larger</span></div><button onclick={resetSelectedGlyphScale} disabled={buildingPreview || selectedGlyph.transform.scaleY === 1}>Reset to 100%</button></section>
      <section class="trace-detail"><h3>Outline detail</h3><p>Choose how closely the vector outline follows the source brush.</p><div>{#each ['preserve', 'balanced', 'smooth'] as preset}<button disabled={buildingPreview} class:active={(selectedGlyph.processing.tracePreset || 'balanced') === preset} onclick={() => setTracePreset(preset as 'preserve' | 'balanced' | 'smooth')}>{buildingPreview ? 'Building…' : preset === 'preserve' ? 'Preserve brush' : preset[0].toUpperCase() + preset.slice(1)}</button>{/each}</div><button class="apply-trace-all" disabled={buildingPreview} onclick={() => setTracePreset('preserve', true)}>{buildingPreview ? 'Rebuilding preview…' : 'Preserve brush on all glyphs'}</button></section>
      <section class="redraw-detail"><h3>Redrawn this template page?</h3><p>Upload the original completed page again. Every glyph on that page will be recreated while saved size, spacing, and outline settings are kept.</p><button class="secondary" onclick={reimportTemplatePages} disabled={importingTemplate}>{importingTemplate ? 'Re-importing…' : 'Re-import template page'}</button></section>
      <dl><div><dt>Source</dt><dd>{selectedGlyph.sourceImagePath || 'Not imported'}</dd></div><div><dt>Advance width</dt><dd>{selectedGlyph.metrics.advanceWidth}</dd></div><div><dt>Side bearings</dt><dd>{selectedGlyph.metrics.leftSideBearing} / {selectedGlyph.metrics.rightSideBearing}</dd></div><div><dt>Threshold</dt><dd>{selectedGlyph.processing.threshold}</dd></div></dl>
    </aside>
  </div>
{/if}
