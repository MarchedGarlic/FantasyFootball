const fs = require('fs-extra');
const path = require('path');

async function build() {
  try {
    console.log('🏗️  Building Fantasy Football Dashboard...');
    
    // Create dist directory
    await fs.ensureDir('dist');
    
    // Find the latest analysis output folder
    const files = await fs.readdir('.');
    const analysisFolders = files.filter(file => 
      file.startsWith('fantasy_analysis_output_') && 
      fs.statSync(file).isDirectory()
    );
    
    if (analysisFolders.length === 0) {
      console.log('❌ No analysis output folders found. Run Python script first!');
      process.exit(1);
    }
    
    // Sort by timestamp and get the latest
    analysisFolders.sort().reverse();
    const latestFolder = analysisFolders[0];
    console.log(`📂 Using latest analysis: ${latestFolder}`);
    
    // Extract timestamp from folder name
    const timestamp = latestFolder.replace('fantasy_analysis_output_', '');
    
    // Copy HTML files to dist with latest naming
    const htmlDir = path.join(latestFolder, 'html_reports');
    const fileMapping = {};
    
    if (await fs.pathExists(htmlDir)) {
      const htmlFiles = await fs.readdir(htmlDir);
      for (const file of htmlFiles) {
        if (file.endsWith('.html')) {
          let newName;
          // Handle files with their own timestamps (like power_ranking_leaderboard)
          if (file.includes('power_ranking_leaderboard')) {
            newName = 'power_ranking_leaderboard_latest.html';
          } else if (file.includes('luck_analysis')) {
            newName = 'luck_analysis_latest.html';
          } else {
            const baseName = file.replace(`_${timestamp}.html`, '');
            newName = `${baseName}_latest.html`;
          }
          await fs.copy(path.join(htmlDir, file), path.join('dist', newName));
          fileMapping[file] = newName;
          console.log(`✓ Copied ${file} → ${newName}`);
        }
      }
    }
    
    // Copy JSON data for API access
    const jsonDir = path.join(latestFolder, 'json_data');
    if (await fs.pathExists(jsonDir)) {
      await fs.ensureDir('dist/data');
      const jsonFiles = await fs.readdir(jsonDir);
      for (const file of jsonFiles) {
        if (file.endsWith('.json')) {
          const baseName = file.replace(`_${timestamp}.json`, '');
          const newName = `${baseName}_latest.json`;
          await fs.copy(path.join(jsonDir, file), path.join('dist/data', newName));
          console.log(`✓ Copied ${file} → data/${newName}`);
        }
      }
    }
    
    // Copy text reports
    const textDir = path.join(latestFolder, 'text_reports');
    if (await fs.pathExists(textDir)) {
      await fs.ensureDir('dist/reports');
      const textFiles = await fs.readdir(textDir);
      for (const file of textFiles) {
        if (file.endsWith('.txt')) {
          const baseName = file.replace(`_${timestamp}.txt`, '');
          const newName = `${baseName}_latest.txt`;
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