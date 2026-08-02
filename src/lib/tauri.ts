import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { revealItemInDir } from '@tauri-apps/plugin-opener';
import type { CompileResult, FontProject, TemplateGenerationResult, TemplateImportResult } from './types';

export const isTauri = () => '__TAURI_INTERNALS__' in window;

export async function chooseProjectFolder(): Promise<string | null> {
  if (!isTauri()) return null;
  const result = await open({ directory: true, multiple: false, title: 'Choose a folder for your font project' });
  return typeof result === 'string' ? result : null;
}

export async function createProjectFolder(path: string, project: FontProject): Promise<void> {
  await invoke('create_project', { path, project });
}

export async function loadProject(path: string): Promise<FontProject> {
  return invoke<FontProject>('load_project', { path });
}

export async function saveProject(path: string, project: FontProject): Promise<void> {
  await invoke('save_project', { path, project: { ...project, updatedAt: new Date().toISOString() } });
}

export async function generateTemplate(path: string, characters: string, preset: string, variants: number, referenceLetters: boolean): Promise<TemplateGenerationResult> {
  return invoke<TemplateGenerationResult>('run_compiler', { request: { command: 'generate-template', projectPath: path, styleId: 'regular', characters, preset, variants, referenceLetters } });
}

export async function generateReplacementTemplate(path: string, glyphs: Array<{ character: string; glyphName: string; variantIndex: number }>, preset = 'a4-portrait'): Promise<TemplateGenerationResult> {
  return invoke<TemplateGenerationResult>('run_compiler', { request: { command: 'generate-replacement-template', projectPath: path, styleId: 'regular', glyphs, preset, referenceLetters: true } });
}

export async function chooseFilledTemplates(): Promise<string[]> {
  if (!isTauri()) return [];
  const result = await open({ multiple: true, directory: false, title: 'Select all completed template pages', filters: [{ name: 'Template images', extensions: ['png', 'jpg', 'jpeg'] }] });
  if (Array.isArray(result)) return result;
  return typeof result === 'string' ? [result] : [];
}

export async function importFilledTemplate(projectPath: string, inputPath: string, importMode: 'standard' | 'reimport' = 'standard'): Promise<TemplateImportResult> {
  return invoke<TemplateImportResult>('run_compiler', { request: { command: 'import-template', projectPath, inputPath, threshold: 160, importMode } });
}

export async function compileFont(projectPath: string, outputDirectory?: string): Promise<CompileResult> {
  return invoke<CompileResult>('run_compiler', { request: { command: 'compile-font', projectPath, styleId: 'regular', outputDirectory } });
}

export async function readProjectBinary(projectPath: string, filePath: string): Promise<Uint8Array> {
  const bytes = await invoke<number[]>('read_project_binary', { projectPath, filePath });
  return new Uint8Array(bytes);
}

export async function revealProjectFile(filePath: string): Promise<void> {
  if (!isTauri()) return;
  await revealItemInDir(filePath);
}
