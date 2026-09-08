---
name: Civic Precision
colors:
  surface: '#FFFFFF'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#3f4850'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#707881'
  outline-variant: '#bfc7d2'
  surface-tint: '#006398'
  primary: '#006194'
  on-primary: '#ffffff'
  primary-container: '#007bb9'
  on-primary-container: '#fdfcff'
  inverse-primary: '#93ccff'
  secondary: '#006399'
  on-secondary: '#ffffff'
  secondary-container: '#7bc2ff'
  on-secondary-container: '#004f7b'
  tertiary: '#894d00'
  on-tertiary: '#ffffff'
  tertiary-container: '#ac6200'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cce5ff'
  primary-fixed-dim: '#93ccff'
  on-primary-fixed: '#001d31'
  on-primary-fixed-variant: '#004b73'
  secondary-fixed: '#cde5ff'
  secondary-fixed-dim: '#94ccff'
  on-secondary-fixed: '#001d32'
  on-secondary-fixed-variant: '#004b74'
  tertiary-fixed: '#ffdcc0'
  tertiary-fixed-dim: '#ffb875'
  on-tertiary-fixed: '#2d1600'
  on-tertiary-fixed-variant: '#6b3b00'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
  bg-main: '#F8FAFC'
  border-subtle: '#E2E8F0'
  text-primary: '#0F172A'
  text-secondary: '#475569'
  text-muted: '#64748B'
  severity-low-text: '#059669'
  severity-low-bg: '#ECFDF5'
  severity-low-border: '#A7F3D0'
  severity-med-text: '#D97706'
  severity-med-bg: '#FFFBEB'
  severity-med-border: '#FDE68A'
  severity-high-text: '#DC2626'
  severity-high-bg: '#FEF2F2'
  severity-high-border: '#FECACA'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-mono-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  data-mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 16px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-2xs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  gutter-app: 1rem
  workbench-gap: 1.5rem
---

# DESIGN SYSTEM — JalanPantau (Deteksi Kerusakan Jalan Real-Time)

## Identitas & Nuansa
- **Karakter**: Civic-tech profesional, alat kerja inspeksi lapangan & dashboard analisis teknis. Bersih, fungsional, tegas, bukan landing marketing atau SaaS generik.
- **Tema**: Terang (Light Mode), kontras teks WCAG AA (≥ 4.5:1), border halus dan tegas, visual hierarchy jelas.
- **Ikonografi**: SVG inline fungsional (Lucide-style/Heroicons), tanpa emoji.

## Palet Warna
- **Background Utama**: `#F8FAFC` (Slate 50)
- **Surface / Card**: `#FFFFFF` (Putih murni dengan border `#E2E8F0`)
- **Primary / Brand**: `#0284C7` (Sky 600) / `#0369A1` (Sky 700) untuk aksi teknis dan akurasi
- **Teks Utama**: `#0F172A` (Slate 900)
- **Teks Sekunder**: `#475569` (Slate 600) / `#64748B` (Slate 500)
- **Severity Colors (Standar Teknis Bina Marga / Jalan)**:
  - **Ringan**: Badge hijau/emerald (`#059669`, bg: `#ECFDF5`, border: `#A7F3D0`)
  - **Sedang**: Badge amber/kuning (`#D97706`, bg: `#FFFBEB`, border: `#FDE68A`)
  - **Berat**: Badge merah/rose (`#DC2626`, bg: `#FEF2F2`, border: `#FECACA`)
- **Border & Pembatas**: `#E2E8F0` (Slate 200)

## Tipografi
- **Font Stack**: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif
- **Heading**: font-bold tracking-tight text-slate-900
- **Body & Data**: font-normal text-slate-700, data monospaced untuk koordinat, confidence, FPS, dan nilai rupiah (`font-mono`)

## Komponen Khas
- **App Bar**: Brand "JalanPantau" dengan badge civic-tech, tab navigasi aktif (Deteksi, Peta, Riwayat, Tentang).
- **Workbench 2 Kolom**: Sisi kiri viewer foto dengan floating toolbar zoom overlay, sisi kanan panel kontrol parameter & input upload.
- **Panel Hasil Bawah**: KPI cards (Jumlah temuan, Prioritas berat, Estimasi total biaya) + Tabel data temuan terperinci.
- **Badge Severity**: Pill badge rounded-full dengan dot indikator warna.
