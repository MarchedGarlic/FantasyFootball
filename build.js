const fs = require('fs-extra');
const path = require('path');

async function build() {
  try {
    console.log('Building Fantasy Football Dashboard...');

    await fs.ensureDir('dist');

    // Analysis output is now keyed by (league_id, season) - see CLAUDE.md section 3.1 - so this
    // reads league_config.json (written by the last `python main.py` run) to know which
    // league_id/season folder to pull from, instead of assuming one fixed flat folder.
    const configPath = 'league_config.json';
    if (!fs.existsSync(configPath)) {
      console.log('No league_config.json found. Run the Python analysis first!');
      process.exit(1);
    }

    const config = await fs.readJson(configPath);
    const leagueId = config.league_id;
    const season = config.target_season;

    if (!leagueId || !season) {
      console.log('league_config.json is missing league_id or target_season.');
      process.exit(1);
    }

    const analysisFolder = path.join('fantasy_analysis_output', 'leagues', String(leagueId), String(season));

    if (!fs.existsSync(analysisFolder)) {
      console.log(`No analysis output folder found at ${analysisFolder}. Run Python script first!`);
      process.exit(1);
    }

    console.log(`Using analysis folder: ${analysisFolder} (league ${leagueId}, season ${season})`);

    // Copy HTML files to dist with latest naming
    const htmlDir = path.join(analysisFolder, 'html_reports');

    if (await fs.pathExists(htmlDir)) {
      const htmlFiles = await fs.readdir(htmlDir);
      for (const file of htmlFiles) {
        if (file.endsWith('.html')) {
          const newName = file.replace('.html', '_latest.html');
          await fs.copy(path.join(htmlDir, file), path.join('dist', newName));
          console.log(`Copied ${file} -> ${newName}`);
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
          console.log(`Copied ${file} -> data/${newName}`);
        }
      }
    }

    // Copy text reports (.txt and .md - the latter added for weekly_digest.md, the raw
    // Markdown behind the Weekly Digest export page's copy/download buttons)
    const textDir = path.join(analysisFolder, 'text_reports');
    if (await fs.pathExists(textDir)) {
      await fs.ensureDir('dist/reports');
      const textFiles = await fs.readdir(textDir);
      for (const file of textFiles) {
        const ext = file.endsWith('.txt') ? '.txt' : file.endsWith('.md') ? '.md' : null;
        if (ext) {
          const newName = file.replace(ext, `_latest${ext}`);
          await fs.copy(path.join(textDir, file), path.join('dist/reports', newName));
          console.log(`Copied ${file} -> reports/${newName}`);
        }
      }
    }

    // Record which league/season this static build represents, so the static frontend can
    // show it without needing a live API call.
    await fs.writeJson('dist/data/build_info.json', {
      league_id: leagueId,
      season: season,
      league_name: config.league_name || null,
      built_at: new Date().toISOString(),
    }, { spaces: 2 });

    await fs.copy('index.html', 'dist/index.html');
    console.log('Copied index.html');

    if (await fs.pathExists('results_template.html')) {
      await fs.copy('results_template.html', 'dist/results.html');
      console.log('Copied results template');
    }

    console.log('Build complete! Files ready for deployment.');

  } catch (error) {
    console.error('Build failed:', error.message);
    process.exit(1);
  }
}

build();
