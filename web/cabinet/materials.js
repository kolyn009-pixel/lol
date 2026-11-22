/* Browsing uses the same library and file endpoints as the teacher cabinet. */
(function () {
  'use strict';
  var categories = [['materials', 'Материалы'], ['collections', 'Сборники'], ['tasks', 'Банк задач']];
  var classic = C.legacy('teacher', 'library');

  function materialLink(item) {
    if (item.material_type === 'PDF' && Number(item.id) > 0) {
      return '/api/teacher/material/file?id=' + encodeURIComponent(item.id);
    }
    try {
      var url = new URL(item.external_url);
      return ['https:', 'http:'].includes(url.protocol) ? url.href : '';
    } catch (_) { return ''; }
  }

  function material(item) {
    var row = C.el('article', 'c-row'), info = C.el('div', 'c-row-t');
    info.append(C.el('b', '', item.title || 'Материал'), C.el('p', 'c-row-s', [C.subjectLabel(item.subject), item.description].filter(Boolean).join(' · ')));
    row.appendChild(info);
    var href = materialLink(item);
    if (href) {
      var link = C.button(item.material_type === 'PDF' ? 'Открыть PDF' : 'Открыть', 'secondary', href);
      link.target = '_blank'; link.rel = 'noopener noreferrer'; row.appendChild(link);
    }
    return row;
  }

  function task(item) {
    var row = C.el('details', 'c-section');
    row.append(C.el('summary', '', item.title || item.source_label || 'Задача'),
      C.el('p', 'c-row-s', [C.subjectLabel(item.subject), item.topic].filter(Boolean).join(' · ')));
    if (item.statement) row.appendChild(C.el('p', '', item.statement));
    if (item.answer) row.appendChild(C.el('p', '', 'Ответ: ' + item.answer));
    return row;
  }

  function render(main) {
    var controls = C.el('form', 'stu-filters'), query = C.el('input'), subject = C.el('select'), section = C.el('select');
    query.type = 'search'; query.maxLength = 200; query.placeholder = 'Поиск в библиотеке';
    query.setAttribute('aria-label', 'Поиск в библиотеке');
    subject.setAttribute('aria-label', 'Предмет');
    [['', 'Все предметы'], ['PHYSICS', 'Физика'], ['CHEMISTRY', 'Химия'], ['MATH', 'Математика']].forEach(function (entry) {
      subject.appendChild(new Option(entry[1], entry[0]));
    });
    section.setAttribute('aria-label', 'Раздел библиотеки');
    categories.forEach(function (entry) { section.appendChild(new Option(entry[1], entry[0])); });
    var submit = C.button('Найти', 'secondary'); submit.type = 'submit';
    controls.append(query, subject, section, submit);
    var results = C.el('div'), data = {}, request = 0;
    results.setAttribute('aria-live', 'polite');
    var actions = C.el('div', 'c-actions');
    actions.append(C.button('Управление библиотекой', 'secondary', classic),
      C.button('Формулы', 'text', C.legacy('teacher', 'formulas')),
      C.button('Задать работу', 'text', C.legacy('teacher', 'homework')));
    main.append(actions, controls, results);

    function fail(error, retry) {
      if (error.status === 401) { location.replace(classic); return; }
      results.replaceChildren(C.error(error.message, retry));
    }

    function showCollection(item) {
      var current = ++request;
      results.replaceChildren(C.el('div', 'c-skel'));
      C.api('/teacher/library/collection/detail?id=' + encodeURIComponent(item.id)).then(function (d) {
        if (current !== request) return;
        results.replaceChildren(C.button('← К сборникам', 'text', paint), C.el('h2', '', d.collection?.title || item.title));
        if (d.collection?.description) results.appendChild(C.el('p', '', d.collection.description));
        [['Материалы', d.materials, material], ['Задачи', d.tasks, task]].forEach(function (entry) {
          var block = C.section('', entry[0]);
          (entry[1] || []).forEach(function (row) { block.appendChild(entry[2](row)); });
          if (!entry[1]?.length) block.appendChild(C.empty('В этом разделе пока пусто.'));
          results.appendChild(block);
        });
      }, function (error) { if (current === request) fail(error, function () { showCollection(item); }); });
    }

    function collection(item) {
      var row = C.el('article', 'c-row'), info = C.el('div', 'c-row-t');
      info.append(C.el('b', '', item.title || 'Сборник'), C.el('p', 'c-row-s', 'Материалов: ' + (item.material_count || 0) + ' · задач: ' + (item.task_count || 0)));
      row.append(info, C.button('Открыть', 'secondary', function () { showCollection(item); }));
      return row;
    }

    function paint() {
      var items = data[section.value] || [];
      var row = { materials: material, collections: collection, tasks: task }[section.value];
      results.replaceChildren.apply(results, items.length ? items.map(row) : [C.empty('Ничего не найдено.')]);
    }

    function load() {
      var current = ++request;
      results.replaceChildren(C.el('div', 'c-skel'));
      var params = new URLSearchParams({ q: query.value.trim(), subject: subject.value });
      return C.api('/teacher/library/overview?' + params).then(function (d) {
        if (current !== request) return;
        data = d; paint();
      }, function (error) { if (current === request) fail(error, load); });
    }

    controls.addEventListener('submit', function (event) { event.preventDefault(); load(); });
    section.addEventListener('change', load);
    subject.addEventListener('change', load);
    return load();
  }
  window.CabMaterials = { render: render };
})();
