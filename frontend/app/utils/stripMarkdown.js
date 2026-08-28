/**
 * Strip markdown formatting from text to display clean plain text.
 * Removes ##, --, **, *, ``, [], links, horizontal rules, etc.
 */
export function stripMarkdown(text) {
  if (!text || typeof text !== 'string') return text

  let cleaned = text

  // Remove thinking/reasoning blocks
  cleaned = cleaned.replace(/<think>[\s\S]*?<\/think>/gi, '').trim()

  // Remove markdown headers (##, ###, etc.)
  cleaned = cleaned.replace(/^#{1,6}\s+/gm, '')

  // Remove bold/italic markers
  cleaned = cleaned.replace(/\*\*\*([^*]+)\*\*\*/g, '$1')
  cleaned = cleaned.replace(/\*\*([^*]+)\*\*/g, '$1')
  cleaned = cleaned.replace(/\*([^*]+)\*/g, '$1')
  cleaned = cleaned.replace(/___([^_]+)___/g, '$1')
  cleaned = cleaned.replace(/__([^_]+)__/g, '$1')
  cleaned = cleaned.replace(/_([^_]+)_/g, '$1')

  // Remove inline code backticks
  cleaned = cleaned.replace(/`([^`]+)`/g, '$1')

  // Remove code blocks
  cleaned = cleaned.replace(/```[\s\S]*?```/g, '')

  // Remove markdown links [text](url) -> text
  cleaned = cleaned.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')

  // Remove images ![alt](url)
  cleaned = cleaned.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')

  // Remove horizontal rules (---, ***, ___)
  cleaned = cleaned.replace(/^[\s]*[-*_]{3,}\s*$/gm, '')

  // Remove blockquotes
  cleaned = cleaned.replace(/^>\s+/gm, '')

  // Remove unordered list markers
  cleaned = cleaned.replace(/^[\s]*[-+*]\s+/gm, '')

  // Remove ordered list markers
  cleaned = cleaned.replace(/^[\s]*\d+\.\s+/gm, '')

  // Remove strikethrough
  cleaned = cleaned.replace(/~~([^~]+)~~/g, '$1')

  // Remove any remaining standalone ** or * or `
  cleaned = cleaned.replace(/\*{1,2}/g, '')
  cleaned = cleaned.replace(/`/g, '')

  // Remove excessive whitespace but preserve single newlines
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n')
  cleaned = cleaned.trim()

  return cleaned
}
