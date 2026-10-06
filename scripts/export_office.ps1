param(
  [Parameter(Mandatory=$true)][string]$InputDirectory,
  [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference='Stop'
$inputPath=[IO.Path]::GetFullPath($InputDirectory)
$outputPath=[IO.Path]::GetFullPath($OutputDirectory)
if ($inputPath -eq $outputPath) { throw 'Choose a separate export directory / 使用独立导出目录' }
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
# Create and close only the Office instances owned by this script.
# 只创建及关闭本脚本自己的Office实例。
$word=$null
$ppt=$null
try {
  $word=New-Object -ComObject Word.Application
  $word.Visible=$false
  $word.DisplayAlerts=0
  foreach ($file in Get-ChildItem -LiteralPath $inputPath -Filter '*.docx' -File) {
    $document=$word.Documents.Open($file.FullName,$false,$true)
    try {
      $document.Fields.Update() | Out-Null
      $pdf=Join-Path $outputPath ($file.BaseName+'_word.pdf')
      if (Test-Path -LiteralPath $pdf) { throw 'Export exists; choose a new folder' }
      $document.ExportAsFixedFormat($pdf,17)
    } finally { $document.Close(0) }
  }
  $ppt=New-Object -ComObject PowerPoint.Application
  foreach ($file in Get-ChildItem -LiteralPath $inputPath -Filter '*.pptx' -File) {
    $presentation=$ppt.Presentations.Open($file.FullName,$true,$false,$false)
    try {
      $pdf=Join-Path $outputPath ($file.BaseName+'_slides.pdf')
      $images=Join-Path $outputPath ($file.BaseName+'_slide_images')
      if ((Test-Path -LiteralPath $pdf) -or (Test-Path -LiteralPath $images)) { throw 'Export exists; choose a new folder' }
      $presentation.SaveAs($pdf,32)
      $presentation.Export($images,'PNG',1920,1080)
    } finally { $presentation.Close() }
  }
} finally {
  if ($word) { $word.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
  if ($ppt) { $ppt.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($ppt) }
}
