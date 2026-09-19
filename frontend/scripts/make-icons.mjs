/**
 * Generate the App Store icon and the launch image.
 *
 * The mark is a goal post seen head-on, in the site's marker orange on its own
 * near-black. It is the one piece of football furniture that is a clean
 * geometric shape rather than a drawing, so it survives being shrunk to the
 * 60pt a home screen draws — where a helmet or a ball becomes a brown smudge.
 *
 * The accent is spent here and nowhere else, which is the same rule the product
 * follows: one colour, on the one thing that matters.
 *
 * Apple requires the 1024pt icon to be opaque with square corners — iOS applies
 * the rounded mask itself.
 *
 * Run: node scripts/make-icons.mjs
 */
import sharp from 'sharp'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const PAGE = '#0e0f11'
const RAISED = '#1b1d21'
const ACCENT = '#f2795a'
const LINE = '#e8e6e3'

const ICONSET = join(process.cwd(), 'ios/App/App/Assets.xcassets/AppIcon.appiconset')
const SPLASHSET = join(process.cwd(), 'ios/App/App/Assets.xcassets/Splash.imageset')

const scene = (S, k, lit = true) => {
  const c = S / 2
  const u = (S * k) / 1000
  const px = (n) => +(n * u).toFixed(2)

  const bar = px(96)          // stroke weight, heavy enough to hold at 60pt
  const half = bar / 2
  const uprightH = px(560)    // the two verticals
  const crossW = px(620)      // the crossbar
  const postH = px(250)       // the stem below the crossbar
  const crossY = 0            // everything is measured from the crossbar

  const top = crossY - uprightH - half
  const bottom = crossY + postH + half
  const shift = -(top + bottom) / 2

  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">
  <defs>
    <radialGradient id="ground" cx="50%" cy="38%" r="80%">
      <stop offset="0%" stop-color="${RAISED}"/>
      <stop offset="100%" stop-color="${PAGE}"/>
    </radialGradient>
    <radialGradient id="halo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${ACCENT}" stop-opacity="${lit ? 0.3 : 0.2}"/>
      <stop offset="100%" stop-color="${ACCENT}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="${S}" height="${S}" fill="url(#ground)"/>

  <g transform="translate(${c} ${c + shift})">
    <ellipse cx="0" cy="${crossY}" rx="${px(760)}" ry="${px(560)}" fill="url(#halo)"/>

    <!-- crossbar -->
    <rect x="${-crossW / 2}" y="${crossY - half}" width="${crossW}" height="${bar}" rx="${half}" fill="${ACCENT}"/>
    <!-- uprights -->
    <rect x="${-crossW / 2}" y="${crossY - uprightH}" width="${bar}" height="${uprightH}" rx="${half}" fill="${ACCENT}"/>
    <rect x="${crossW / 2 - bar}" y="${crossY - uprightH}" width="${bar}" height="${uprightH}" rx="${half}" fill="${ACCENT}"/>
    <!-- the stem, and the base it stands on -->
    <rect x="${-half}" y="${crossY}" width="${bar}" height="${postH}" rx="${half}" fill="${ACCENT}"/>
    <rect x="${-px(230)}" y="${crossY + postH - px(14)}" width="${px(460)}" height="${px(28)}" rx="${px(14)}" fill="${LINE}" opacity="0.5"/>
  </g>
</svg>`)
}

await sharp(scene(1024, 0.78)).flatten({ background: PAGE }).png({ compressionLevel: 9 })
  .toFile(join(ICONSET, 'AppIcon-512@2x.png'))
console.log('  AppIcon-512@2x.png            1024x1024')

const splash = await sharp(scene(2732, 0.2, false)).flatten({ background: PAGE }).png({ compressionLevel: 9 }).toBuffer()
for (const name of ['splash-2732x2732.png', 'splash-2732x2732-1.png', 'splash-2732x2732-2.png']) {
  await writeFile(join(SPLASHSET, name), splash)
  console.log(`  ${name.padEnd(30)}2732x2732`)
}

await sharp(scene(1024, 0.78)).flatten({ background: PAGE }).resize(60, 60).png()
  .toFile(join(process.cwd(), 'review-shots', 'icon-60pt.png'))
console.log('\n  review-shots/icon-60pt.png    60x60 (home-screen check)')
