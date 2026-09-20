// Pure role and bounded DOM contracts. This is not native rendering evidence.
const assert = require('node:assert/strict');
const path = require('node:path');
const { DocumentDouble, append } = require('./dom-double.cjs');
const { indexedDBDouble, storageWindow } = require('./reader-storage.cjs');
const compiled = process.argv[2];
const T = require(path.join(compiled, 'theme.js'));
const P = require(path.join(compiled, 'preferences.js'));
function luminance(hex) { const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4); return c[0] * .2126 + c[1] * .7152 + c[2] * .0722; }
function contrast(a, b) { const l = [luminance(a), luminance(b)].sort((a, b) => b - a); return (l[0] + .05) / (l[1] + .05); }
function documentWithStorage(factory = indexedDBDouble(), legacy = []) {
  const document = new DocumentDouble(), backing = storageWindow(factory, legacy);
  Object.assign(document.defaultView, backing);
  document.defaultView.getComputedStyle = element => ({ getPropertyValue(name) {
    for (let current = element; current; current = current.parentElement) {
      const inline = current.style.getPropertyValue(name); if (inline) return inline;
      const preset = T.themePresets.find(preset => preset.id === current.getAttribute('data-av-palette'));
      if (preset && T.themeColorProperties(preset.colors)[name]) return T.themeColorProperties(preset.colors)[name];
    }
    return '';
  } });
  return { document, backing };
}
function setting(surface, key, value) { return append(surface, 'input', { 'data-av-setting': key, type: 'radio', value }); }
function choose(controller, input) { input.checked = true; controller.change(input); }
function surface(document, parent, id, attributes = {}) { return append(parent || document.body, 'div', { id, class: 'av-surface', 'data-av-preferences': '', 'data-av-theme':'light', 'data-av-palette':'indigo', ...attributes }); }

async function run() {
  const variants = [...T.themePresets.map(preset => preset.colors),
    {main:'#ffffff', secondary:'#ffffff', tertiary:'#ffffff'},
    {main:'#000000', secondary:'#000000', tertiary:'#000000'},
    {main:'#ffffff', secondary:'#000000', tertiary:'#ffff00'},
    {main:'#ff0000', secondary:'#00ff00', tertiary:'#0000ff'},
    ...['#000000','#ffffff','#777777','#8ccaff','#f7ede3','#142b24'].map(background => ({main:'#6750e8',secondary:'#008596',tertiary:'#de587f',backgroundLight:background,backgroundDark:background}))];
  for (const colors of variants) for (const mode of ['light', 'dark']) {
    const roles = T.resolveTheme(colors, mode);
    for (const foreground of ['ink','muted','accent','secondary','tertiary','heading','subheading','tool-ink','inspector-ink']) {
      for (const background of Object.keys(T.themeSurfaceRoles).filter(name => !name.startsWith('heat-'))) assert(contrast(roles[foreground], roles[background]) >= 4.5, `${foreground}/${background} ${mode} ${JSON.stringify(colors)}`);
    }
    assert(luminance(roles['heat-low']) > luminance(roles['heat-high']), 'Even an all-white custom palette must retain an ordered heat scale');
    assert(contrast(roles['heat-ink'],roles['heat-high']) >= 4.5);
    assert.equal(roles['image-paper'], '#ffffff');
    if(colors.backgroundLight==='#000000'||colors.backgroundLight==='#ffffff') assert.notEqual(roles.sheet,roles.paper,'Custom extremes retain raised surfaces');
    for(let slot=1;slot<=6;slot++) assert(contrast(roles['series-'+slot],roles.plot)>=3,`Category ${slot} must remain visible on ${roles.plot}`);
    for(const name of ['sage','brass','failure','uncertain','mineral']) {
      assert(contrast(roles[name],roles[name+'-pale'])>=4.5,`Semantic ${name} badge`);
      if(colors.backgroundLight||colors.backgroundDark)for(const surface of ['paper','sheet','plot','subtle'])assert(contrast(roles[name],roles[surface])>=4.5,`Semantic ${name}/${surface}`);
    }
    const reference = T.resolveTheme(T.themePresets[0].colors, mode);
    if(!colors.backgroundLight&&!colors.backgroundDark) for (const role of ['sage','sage-pale','brass','brass-pale','failure','failure-pale','uncertain','uncertain-pale']) assert.equal(roles[role], reference[role]);
  }
  const original = T.themePresets[0].colors;
  for (const [key, role] of [['main','paper'],['secondary','tool-surface'],['tertiary','inspector-surface']]) {
    for (const mode of ['light','dark']) assert.notEqual(T.resolveTheme(original,mode)[role], T.resolveTheme({...original,[key]:'#ffcc00'},mode)[role], `${key} must reach ${role}`);
  }
  assert.equal(new Set(T.themePresets.map(p => T.resolveTheme(p.colors,'light').paper)).size, T.themePresets.length);
  const settings = P.appearanceSettings({id:'controls'});
  for (const choice of T.themePresets) assert(settings.includes(`value="${choice.id}"`));
  for (const [key, values] of Object.entries(T.themeChoices)) for (const value of values) assert(settings.includes(`value="${value}" data-av-setting="${key}"`));
  const custom = P.reportSurface({id:'custom',body:'',customColors:{main:'#ffffff',secondary:'#555555',tertiary:'#000000'},canvas:'textured',texture:'grid',intensity:'moderate'});
  assert(custom.includes('--av-tone-paper:light-dark(')); assert(custom.includes('data-av-texture="grid"'));
  assert.throws(() => T.themeColorProperties({...original,main:'red;url(bad)'}), /hex/);
  assert.throws(() => T.themeColorProperties({...original,backgroundDark:'red;url(bad)'}), /hex/);
  for(const key of T.backgroundColorKeys) assert(settings.includes(`data-av-color="${key}"`));
  const backgrounds={...original,backgroundLight:'#f7ede3',backgroundDark:'#142b24'};
  for(const mode of ['light','dark']) { const roles=T.resolveTheme(backgrounds,mode);assert.equal(roles.paper,backgrounds[mode==='light'?'backgroundLight':'backgroundDark']);assert.notEqual(roles.sheet,T.resolveTheme(original,mode).sheet);assert.equal(roles['scroll-track'],roles.paper); }

  // Enhancing a bare frame must preserve its inherited scope without adding defaults.
  {
    const {document} = documentWithStorage();
    const outer = surface(document,null,'outer',{'data-av-theme':'dark','data-av-palette':'rose','data-av-canvas':'plain',style:'--av-palette-paper:#203040;--av-palette-sheet:#304050'});
    const card = append(outer,'section',{class:'av-card'}), controller = P.attachPreferences(card);
    assert.equal(card.getAttribute('data-av-theme'),null); assert.equal(card.getAttribute('data-av-palette'),null);
    const dialog = append(document.body,'dialog',{class:'av-focus-dialog'}); dialog.appendChild(card); controller.mirror(dialog,card);
    assert.equal(dialog.getAttribute('data-av-theme'),'dark'); assert.equal(dialog.getAttribute('data-av-palette'),'rose'); assert.equal(dialog.getAttribute('data-av-canvas'),'plain');
    assert.equal(dialog.style.getPropertyValue('--av-palette-paper'),'#203040'); assert.equal(dialog.style.getPropertyValue('--av-palette-sheet'),'#304050');
    assert.equal(outer.getAttribute('data-av-theme'),'dark'); controller.cleanup();
  }
  // Every supported primitive survives movement, including a nearer author override.
  {
    const {document} = documentWithStorage(), root = append(document.body,'main',{class:'av-report'});
    const one = surface(document,root,'one',{'data-av-theme':'dark','data-av-palette':'ocean'});
    for (const [i,name] of T.supportedThemePrimitives.entries()) one.style.setProperty(name, `rgb(${i}, 40, 60)`);
    const intermediate = append(one,'div',{style:'--av-palette-paper:#abcdef'});
    const card = append(intermediate,'section',{class:'av-card',style:'--av-palette-heading:#fedcba'});
    const two = surface(document,root,'two',{'data-av-palette':'citrus'}), other = append(two,'section',{class:'av-card'});
    const palette = setting(one,'palette','rose'), controller = P.attachPreferences(root), dialog = append(root,'dialog',{class:'av-focus-dialog'});
    dialog.appendChild(card); controller.mirror(dialog,card);
    assert.equal(dialog.style.getPropertyValue('--av-palette-paper'),'#abcdef'); assert.equal(dialog.style.getPropertyValue('--av-palette-heading'),'#fedcba');
    for (const name of T.supportedThemePrimitives) assert(dialog.style.getPropertyValue(name),name);
    choose(controller,palette); assert.equal(dialog.getAttribute('data-av-palette'),'rose'); assert.equal(dialog.style.getPropertyValue('--av-palette-paper'),'#abcdef');
    dialog.appendChild(other); controller.mirror(dialog,other);
    for (const name of T.supportedThemePrimitives) assert.equal(dialog.style.getPropertyValue(name),'',`stale ${name}`);
    controller.cleanup(); assert.equal(one.style.getPropertyValue('--av-palette-paper'),'rgb(0, 40, 60)');
  }
  // Mode options and custom tones apply to the actual scope and to existing mirrors.
  {
    const {document} = documentWithStorage(), root = surface(document,null,'options');
    const textureOptions = append(root,'div',{'data-av-texture-options':'',hidden:''}), intensityOptions = append(root,'div',{'data-av-intensity-options':''});
    const textured = setting(root,'canvas','textured'), plain = setting(root,'canvas','plain'), grid = setting(root,'texture','grid'), moderate = setting(root,'intensity','moderate');
    const backgroundColor = append(root,'input',{'data-av-color':'backgroundDark',value:'#142b24'});
    const customChoice = setting(root,'palette','custom'), color = append(root,'input',{'data-av-color':'tertiary',value:'#113355'}), card = append(root,'section',{class:'av-card'});
    const controller = P.attachPreferences(root), dialog = append(document.body,'dialog',{}); dialog.appendChild(card); controller.mirror(dialog,card);
    choose(controller,textured); choose(controller,grid); choose(controller,moderate); assert.equal(textureOptions.hidden,false); assert.equal(dialog.getAttribute('data-av-texture'),'grid'); assert.equal(dialog.getAttribute('data-av-intensity'),'moderate');
    choose(controller,customChoice); color.value='#eecb19'; controller.change(color); assert(root.style.getPropertyValue('--av-tone-inspector-surface')); assert.equal(dialog.style.getPropertyValue('--av-tone-inspector-surface'),root.style.getPropertyValue('--av-tone-inspector-surface'));
    backgroundColor.value='#142b24';controller.change(backgroundColor);assert(root.style.getPropertyValue('--av-tone-paper').includes('#142b24'));assert.equal(dialog.style.getPropertyValue('--av-tone-paper'),root.style.getPropertyValue('--av-tone-paper'));
    choose(controller,plain); assert.equal(textureOptions.hidden,true); assert.equal(intensityOptions.hidden,true); controller.cleanup();
  }
  // Standalone page scrollbars follow the report, without taking sibling reports' ownership.
  for (const siblings of [false,true]) {
    const {document}=documentWithStorage();document.documentElement=document.createElement('html');
    document.documentElement.style.setProperty('color-scheme','light');
    const root=surface(document,null,'page',{'class':'av-workspace','data-av-theme':'dark'});
    if(siblings) surface(document,null,'sibling',{'class':'av-workspace'});
    const palette=setting(root,'palette','citrus'),controller=P.attachPreferences(root);
    if(siblings) assert.equal(document.documentElement.getAttribute('data-av-page-scroll'),null);
    else {
      assert.equal(document.documentElement.style.getPropertyValue('color-scheme'),'dark');
      const initial=document.documentElement.style.getPropertyValue('--av-page-scroll-thumb');choose(controller,palette);
      assert.notEqual(document.documentElement.style.getPropertyValue('--av-page-scroll-thumb'),initial);
    }
    controller.cleanup();assert.equal(document.documentElement.style.getPropertyValue('color-scheme'),'light');assert.equal(document.documentElement.style.getPropertyValue('--av-page-scroll-thumb'),'');
  }
  // Two report instances merge independent display changes transactionally.
  {
    const factory = indexedDBDouble(), left = documentWithStorage(factory), right = documentWithStorage(factory);
    const a = surface(left.document,null,'shared',{'data-av-storage-key':'display'}), b = surface(right.document,null,'shared',{'data-av-storage-key':'display'});
    const dark = setting(a,'theme','dark'), grid = setting(b,'texture','grid');
    const ca = P.attachPreferences(a), cb = P.attachPreferences(b); await Promise.all([ca.whenIdle(),cb.whenIdle()]); choose(ca,dark); choose(cb,grid); await Promise.all([ca.whenIdle(),cb.whenIdle()]);
    const third = documentWithStorage(factory), c = surface(third.document,null,'shared',{'data-av-storage-key':'display'}), cc = P.attachPreferences(c); await cc.whenIdle();
    assert.equal(c.getAttribute('data-av-theme'),'dark'); assert.equal(c.getAttribute('data-av-texture'),'grid'); ca.cleanup();cb.cleanup();cc.cleanup();
  }
  // Foreign legacy records remain byte-for-byte untouched; malformed data cannot be overwritten.
  for (const raw of ['{"kind":"notebook","notes":["retained"]}', '{"theme":"dark","secret":"foreign"}', '{broken']) {
    const {document,backing} = documentWithStorage(indexedDBDouble(),[['display',raw]]), root = surface(document,null,'protected',{'data-av-storage-key':'display'});
    const status = append(root,'p',{'data-av-preference-persistence':'',hidden:''}), dark = setting(root,'theme','dark'), controller = P.attachPreferences(root); await controller.whenIdle(); choose(controller,dark); await controller.whenIdle();
    assert.equal(backing.legacy.get('display'),raw); assert.match(status.textContent,/protected/); assert.equal(status.hidden,false); controller.cleanup();
  }
  // Legacy choices are usable without a storage backend, and the UI says saving is unavailable.
  {
    const {document,backing} = documentWithStorage(indexedDBDouble(),[['display','{"theme":"dark","palette":"ocean"}']]);
    document.defaultView.indexedDB.failOpen=true;
    const root = surface(document,null,'legacy',{'data-av-storage-key':'display'}), status=append(root,'p',{'data-av-preference-persistence':'',hidden:''});
    const controller=P.attachPreferences(root); await controller.whenIdle(); assert.equal(root.getAttribute('data-av-theme'),'dark'); assert.match(status.textContent,/unavailable/); assert(backing.legacy.has('display'));controller.cleanup();
  }
  console.log('theme roles, canvas preferences, inherited ownership, custom mirrors and guarded transactional persistence passed (source/DOM doubles only)');
}
run().catch(error => { console.error(error); process.exitCode=1; });
