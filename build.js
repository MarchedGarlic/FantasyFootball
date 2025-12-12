const fs = require('fs-extra');
const path = require('path');

async function build() {
  try {
    console.log('🏗️  Building Fantasy Football Dashboard...');
    
    // Create dist directory
    await fs.ensureDir('dist');
    
    // Use fixed analysis output folder
    const analysisFolder = 'fantasy_analysis_output';
    
    if (!fs.existsSync(analysisFolder)) {
      console.log('❌ No analysis output folder found. Run Python script first!');
      process.exit(1);
    }
    
    console.log(`📂 Using analysis folder: ${analysisFolder}`);
    
    // Copy HTML files to dist with latest naming
    const htmlDir = path.join(analysisFolder, 'html_reports');
    const fileMapping = {};
    
    if (await fs.pathExists(htmlDir)) {
      const htmlFiles = await fs.readdir(htmlDir);
      for (const file of htmlFiles) {
        if (file.endsWith('.html')) {
          // Since we removed timestamps, just use the base filename with _latest suffix
          let newName = file.replace('.html', '_latest.html');
          await fs.copy(path.join(htmlDir, file), path.join('dist', newName));
          fileMapping[file] = newName;
          console.log(`✓ Copied ${file} → ${newName}`);
        }
      }
    }
    
    // Copy JSON data for API access
    const jsonDir = path.join(analysisFolder, 'json_data');
    if (await fs.pathExists(jsonDir)) {
      await fs.ensureDir('dist/data');
      const jsonFiles = await fs.readdir(jsonDir);
      for (const file of jsonFiles) {
        if (file.endsWith('.json')) {
          const newName = file.replace('.json', '_latest.json');
          await fs.copy(path.join(jsonDir, file), path.join('dist/data', newName));
          console.log(`✓ Copied ${file} → data/${newName}`);
        }
      }
    }
    
    // Copy text reports
    const textDir = path.join(analysisFolder, 'text_reports');
    if (await fs.pathExists(textDir)) {
      await fs.ensureDir('dist/reports');
      const textFiles = await fs.readdir(textDir);
      for (const file of textFiles) {
        if (file.endsWith('.txt')) {
          const newName = file.replace('.txt', '_latest.txt');
          await fs.copy(path.join(textDir, file), path.join('dist/reports', newName));
          console.log(`✓ Copied ${file} → reports/${newName}`);
        }
      }
    }
    
    // Copy the main index.html
    await fs.copy('index.html', 'dist/index.html');
    console.log('✓ Copied index.html');
    
    console.log('✅ Build complete! Files ready for deployment.');
    
  } catch (error) {
    console.error('❌ Build failed:', error.message);
    process.exit(1);
  }
}

build();