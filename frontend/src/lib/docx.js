import DOMPurify from 'dompurify'
import {
  AlignmentType,
  Document,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  UnderlineType,
  WidthType,
} from 'docx'

export const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

const MAX_IMAGE_WIDTH = 480
const DEFAULT_IMAGE_WIDTH = 480
const DEFAULT_IMAGE_HEIGHT = 320
const MAX_LIST_LEVEL = 5

const BLOCK_CONTAINER_TAGS = new Set([
  'ADDRESS',
  'ARTICLE',
  'ASIDE',
  'BLOCKQUOTE',
  'DIV',
  'FIGCAPTION',
  'FIGURE',
  'FOOTER',
  'HEADER',
  'MAIN',
  'NAV',
  'P',
  'SECTION',
])

const SANITIZE_OPTIONS = {
  ADD_DATA_URI_TAGS: ['img'],
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick'],
}

const NUMBERING = {
  config: [
    {
      reference: 'trustvault-ordered',
      levels: Array.from({ length: MAX_LIST_LEVEL + 1 }, (_, level) => ({
        level,
        format: LevelFormat.DECIMAL,
        text: `%${level + 1}.`,
        alignment: AlignmentType.START,
        style: {
          paragraph: {
            indent: { left: 720 * (level + 1), hanging: 360 },
          },
        },
      })),
    },
    {
      reference: 'trustvault-bullet',
      levels: Array.from({ length: MAX_LIST_LEVEL + 1 }, (_, level) => ({
        level,
        format: LevelFormat.BULLET,
        text: level % 2 === 0 ? '•' : '◦',
        alignment: AlignmentType.START,
        style: {
          paragraph: {
            indent: { left: 720 * (level + 1), hanging: 360 },
          },
        },
      })),
    },
  ],
}

/**
 * Sanitizes the rich-text HTML produced by the editor before it is displayed or
 * converted. DOCX content is untrusted input, so scripts and event handlers
 * must never reach the DOM.
 */
export function sanitizeEditorHtml(html) {
  return DOMPurify.sanitize(String(html || ''), SANITIZE_OPTIONS)
}

/**
 * Extracts editable HTML from a DOCX blob with mammoth. The result keeps
 * headings, paragraphs, lists, tables, and embedded images, which is the
 * subset the in-browser editor can round-trip. Complex Word layout is not
 * preserved.
 */
export async function extractDocxHtml(blob) {
  const { default: mammoth } = await import('mammoth')
  const arrayBuffer = await blob.arrayBuffer()
  const result = await mammoth.convertToHtml(
    { arrayBuffer },
    {
      styleMap: [
        "p[style-name='Title'] => h1:fresh",
        "p[style-name='Subtitle'] => p:fresh",
        "p[style-name='Heading 1'] => h1:fresh",
        "p[style-name='Heading 2'] => h2:fresh",
        "p[style-name='Heading 3'] => h3:fresh",
      ],
    },
  )
  return {
    html: sanitizeEditorHtml(result.value),
    messages: result.messages || [],
  }
}

function parseHtml(html) {
  const parser = new DOMParser()
  return parser.parseFromString(`<body>${sanitizeEditorHtml(html)}</body>`, 'text/html')
    .body
}

function hasBlockChild(element) {
  return Array.from(element.children).some(
    (child) =>
      BLOCK_CONTAINER_TAGS.has(child.tagName) ||
      /^H[1-6]$/.test(child.tagName) ||
      child.tagName === 'UL' ||
      child.tagName === 'OL' ||
      child.tagName === 'TABLE',
  )
}

function inlineRunsFromNodes(nodes, style = {}, skipLists = false) {
  const runs = []

  for (const node of Array.from(nodes)) {
    if (node.nodeType === 3) {
      const text = node.textContent.replace(/\u00a0/g, ' ')
      if (text) {
        runs.push({ text, ...style })
      }
      continue
    }
    if (node.nodeType !== 1) {
      continue
    }

    const tag = node.tagName
    if (skipLists && (tag === 'UL' || tag === 'OL')) {
      continue
    }
    if (tag === 'BR') {
      runs.push({ break: true })
      continue
    }
    if (tag === 'IMG') {
      runs.push({
        image: node.getAttribute('src') || '',
        alt: node.getAttribute('alt') || '',
        width: Number(node.getAttribute('width')) || null,
        height: Number(node.getAttribute('height')) || null,
      })
      continue
    }

    const nextStyle = { ...style }
    if (tag === 'STRONG' || tag === 'B') {
      nextStyle.bold = true
    }
    if (tag === 'EM' || tag === 'I') {
      nextStyle.italics = true
    }
    if (tag === 'U') {
      nextStyle.underline = true
    }
    if (tag === 'S' || tag === 'STRIKE' || tag === 'DEL') {
      nextStyle.strike = true
    }
    if (tag === 'CODE' || tag === 'KBD' || tag === 'SAMP') {
      nextStyle.font = 'Courier New'
    }
    if (tag === 'A') {
      const href = node.getAttribute('href')
      if (href && /^https?:\/\//i.test(href)) {
        nextStyle.link = href
      }
    }

    runs.push(...inlineRunsFromNodes(node.childNodes, nextStyle, skipLists))
  }

  return runs
}

function decodeDataUrl(src) {
  const match = /^data:image\/(png|jpe?g|gif|bmp);base64,([\s\S]+)$/i.exec(src || '')
  if (!match) {
    return null
  }
  try {
    const binary = atob(match[2].replace(/\s+/g, ''))
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index)
    }
    return {
      bytes,
      type: match[1].toLowerCase() === 'jpeg' ? 'jpg' : match[1].toLowerCase(),
    }
  } catch {
    return null
  }
}

function imageSize(src, width, height) {
  if (width && height) {
    const ratio = Math.min(1, MAX_IMAGE_WIDTH / width)
    return { width: Math.round(width * ratio), height: Math.round(height * ratio) }
  }
  if (typeof Image === 'undefined') {
    return { width: DEFAULT_IMAGE_WIDTH, height: DEFAULT_IMAGE_HEIGHT }
  }
  return new Promise((resolve) => {
    const image = new Image()
    let settled = false
    const finish = (dimensions) => {
      if (!settled) {
        settled = true
        resolve(dimensions)
      }
    }
    image.onload = () => {
      const naturalWidth = image.naturalWidth || DEFAULT_IMAGE_WIDTH
      const naturalHeight = image.naturalHeight || DEFAULT_IMAGE_HEIGHT
      const ratio = Math.min(1, MAX_IMAGE_WIDTH / naturalWidth)
      finish({
        width: Math.round(naturalWidth * ratio),
        height: Math.round(naturalHeight * ratio),
      })
    }
    image.onerror = () =>
      finish({ width: DEFAULT_IMAGE_WIDTH, height: DEFAULT_IMAGE_HEIGHT })
    image.src = src
    // Some browsers never fire load/error for unsupported data URLs.
    setTimeout(
      () => finish({ width: DEFAULT_IMAGE_WIDTH, height: DEFAULT_IMAGE_HEIGHT }),
      3_000,
    )
  })
}

async function imageRunForSrc(src, width, height, alt) {
  const decoded = decodeDataUrl(src)
  if (!decoded) {
    return null
  }
  const dimensions = await imageSize(src, width, height)
  return new ImageRun({
    data: decoded.bytes,
    type: decoded.type,
    transformation: dimensions,
    altText: alt
      ? { name: alt, description: alt, title: alt }
      : undefined,
  })
}

async function runsToDocx(runs) {
  const children = []
  for (const run of runs) {
    if (run.break) {
      children.push(new TextRun({ break: 1 }))
      continue
    }
    if (run.image) {
      const image = await imageRunForSrc(
        run.image,
        run.width,
        run.height,
        run.alt,
      )
      if (image) {
        children.push(image)
      }
      continue
    }
    if (!run.text) {
      continue
    }
    children.push(
      new TextRun({
        text: run.text,
        bold: Boolean(run.bold),
        italics: Boolean(run.italics),
        strike: Boolean(run.strike),
        underline: run.underline
          ? { type: UnderlineType.SINGLE }
          : undefined,
        font: run.font,
        link: run.link,
      }),
    )
  }
  return children
}

async function tableToDocx(tableElement) {
  const rows = []
  for (const rowElement of Array.from(tableElement.querySelectorAll('tr'))) {
    const cells = []
    for (const cellElement of Array.from(rowElement.querySelectorAll('th,td'))) {
      const runs = inlineRunsFromNodes(cellElement.childNodes)
      const children = await runsToDocx(runs)
      cells.push(
        new TableCell({
          children: [
            new Paragraph({
              children:
                children.length > 0 ? children : [new TextRun({ text: '' })],
            }),
          ],
          shading:
            cellElement.tagName === 'TH' ? { fill: 'F1F5F9' } : undefined,
        }),
      )
    }
    if (cells.length > 0) {
      rows.push(new TableRow({ children: cells }))
    }
  }
  if (rows.length === 0) {
    return null
  }
  return new Table({
    rows,
    width: { size: 100, type: WidthType.PERCENTAGE },
  })
}

async function collectListItems(listElement, ordered, level, blocks) {
  const safeLevel = Math.min(level, MAX_LIST_LEVEL)
  for (const item of Array.from(listElement.children)) {
    if (item.tagName !== 'LI') {
      continue
    }
    const runs = inlineRunsFromNodes(item.childNodes, {}, true)
    blocks.push({
      type: 'listItem',
      ordered,
      level: safeLevel,
      runs,
    })
    for (const nested of Array.from(item.children)) {
      if (nested.tagName === 'UL' || nested.tagName === 'OL') {
        await collectListItems(
          nested,
          nested.tagName === 'OL',
          safeLevel + 1,
          blocks,
        )
      }
    }
  }
}

async function collectBlocks(parent, blocks) {
  for (const node of Array.from(parent.childNodes)) {
    if (node.nodeType === 3) {
      const text = node.textContent.trim()
      if (text) {
        blocks.push({ type: 'paragraph', runs: [{ text }] })
      }
      continue
    }
    if (node.nodeType !== 1) {
      continue
    }

    const tag = node.tagName
    if (/^H[1-6]$/.test(tag)) {
      blocks.push({
        type: 'heading',
        level: Number(tag.slice(1)),
        runs: inlineRunsFromNodes(node.childNodes),
      })
    } else if (tag === 'UL' || tag === 'OL') {
      await collectListItems(node, tag === 'OL', 0, blocks)
    } else if (tag === 'TABLE') {
      blocks.push({ type: 'table', element: node })
    } else if (tag === 'IMG') {
      blocks.push({
        type: 'image',
        src: node.getAttribute('src') || '',
        alt: node.getAttribute('alt') || '',
        width: Number(node.getAttribute('width')) || null,
        height: Number(node.getAttribute('height')) || null,
      })
    } else if (tag === 'BLOCKQUOTE') {
      blocks.push({
        type: 'quote',
        runs: inlineRunsFromNodes(node.childNodes),
      })
    } else if (tag === 'PRE') {
      blocks.push({
        type: 'pre',
        runs: [{ text: node.textContent }],
      })
    } else if (tag === 'HR') {
      blocks.push({ type: 'paragraph', runs: [] })
    } else if (BLOCK_CONTAINER_TAGS.has(tag) && hasBlockChild(node)) {
      await collectBlocks(node, blocks)
    } else {
      blocks.push({
        type: 'paragraph',
        runs: inlineRunsFromNodes(node.childNodes),
      })
    }
  }
}

async function blockToDocx(block) {
  switch (block.type) {
    case 'heading': {
      const children = await runsToDocx(block.runs)
      return new Paragraph({
        heading: HeadingLevel[`HEADING_${block.level}`],
        children,
      })
    }
    case 'listItem':
      return new Paragraph({
        numbering: {
          reference: block.ordered
            ? 'trustvault-ordered'
            : 'trustvault-bullet',
          level: block.level,
        },
        children: await runsToDocx(block.runs),
      })
    case 'table':
      return tableToDocx(block.element)
    case 'image': {
      const image = await imageRunForSrc(
        block.src,
        block.width,
        block.height,
        block.alt,
      )
      return image ? new Paragraph({ children: [image] }) : null
    }
    case 'quote':
      return new Paragraph({
        indent: { left: 720 },
        children: await runsToDocx(block.runs),
      })
    case 'pre':
      return new Paragraph({
        children: [
          new TextRun({
            text: block.runs[0]?.text || '',
            font: 'Courier New',
          }),
        ],
      })
    default:
      return new Paragraph({
        children: await runsToDocx(block.runs),
      })
  }
}

/**
 * Converts sanitized editor HTML into a real DOCX binary. This is a
 * browser-side export, not a full Word layout engine: headings, paragraphs,
 * basic character formatting, lists, tables, and embedded images are written
 * to WordprocessingML, while advanced layout, footnotes, comments, and tracked
 * changes are intentionally not round-tripped.
 */
export async function buildDocxBlob(html, { title } = {}) {
  const body = parseHtml(html)
  const blocks = []
  await collectBlocks(body, blocks)

  const children = []
  for (const block of blocks) {
    const converted = await blockToDocx(block)
    if (converted) {
      children.push(converted)
    }
  }
  if (children.length === 0) {
    children.push(new Paragraph({ children: [new TextRun({ text: '' })] }))
  }

  const document = new Document({
    title: title || 'TrustVault document',
    creator: 'TrustVault',
    numbering: NUMBERING,
    sections: [
      {
        properties: {
          page: {
            margin: {
              top: 720,
              right: 720,
              bottom: 720,
              left: 720,
            },
          },
        },
        children,
      },
    ],
  })

  return Packer.toBlob(document)
}
