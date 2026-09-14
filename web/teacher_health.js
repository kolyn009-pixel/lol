(()=>{
  const root=document.documentElement;

  if(root.dataset.adeliaTeacherHealth){
    return;
  }

  root.dataset.adeliaTeacherHealth='1';

  const esc=s=>String(s??'').replace(
    /[&<>"']/g,
    c=>({
      '&':'&amp;',
      '<':'&lt;',
      '>':'&gt;',
      '"':'&quot;',
      "'":'&#39;'
    }[c])
  );

  const bytes=n=>{
    n=Number(n||0);

    if(!Number.isFinite(n)){
      return '—';
    }

    const units=[
      'Б',
      'КБ',
      'МБ',
      'ГБ',
      'ТБ'
    ];

    let index=0;

    while(
      n>=1024
      && index<units.length-1
    ){
      n/=1024;
      index++;
    }

    return (
      `${n.toFixed(index?1:0)} ${units[index]}`
    );
  };

  async function readJson(
    url,
    options={}
  ){
    const response=await fetch(
      url,
      {
        credentials:'same-origin',
        ...options
      }
    );

    const data=await response
      .json()
      .catch(()=>({}));

    if(!response.ok){
      const error=new Error(
        data.error
        || data.detail
        || `HTTP ${response.status}`
      );

      error.status=response.status;

      throw error;
    }

    return data;
  }

  function oauthNotice(){
    const params=
      new URLSearchParams(
        window.location.search
      );

    const status=params.get('google');

    if(!status){
      return '';
    }

    const messages={
      connected:
        '✓ Google Calendar подключён',
      denied:
        'Google не выдал доступ к календарю.',
      invalid_state:
        'Сессия подключения Google истекла. Запусти подключение ещё раз.',
      auth_required:
        'Сначала войди в кабинет преподавателя.',
      failed:
        'Не удалось завершить подключение Google Calendar.'
    };

    const success=
      status==='connected';

    const text=
      messages[status]
      || 'Статус Google Calendar обновлён.';

    return `
      <div
        class="${
          success
            ? 'health-ok'
            : 'health-warning'
        } health-google-notice"
      >
        ${esc(text)}
      </div>
    `;
  }

  function googlePanel(status){
    if(!status){
      return `
        <article
          class="health-panel health-google"
        >
          <h3>Google Calendar</h3>

          <div class="health-warning">
            Не удалось получить статус интеграции.
          </div>
        </article>
      `;
    }

    const connected=
      Boolean(status.connected);

    const configured=
      Boolean(status.oauth_configured);

    const stateText=
      connected
        ? 'Подключён'
        : 'Не подключён';

    let detail='';

    if(connected){
      detail=
        `Календарь: ${
          esc(
            status.calendar_id
            || 'primary'
          )
        }${
          status.refresh_token
            ? ' · refresh token есть'
            : ''
        }`;
    }else if(configured){
      detail=
        'OAuth-клиент готов. Можно подключить календарь.';
    }else{
      detail=
        'OAuth credentials ещё не настроены на сервере.';
    }

    const action=configured
      ? `
        <button
          class="${
            connected
              ? 'soft'
              : 'primary'
          }"
          id="googleCalendarConnect"
        >
          ${
            connected
              ? 'Переподключить'
              : 'Подключить Google Calendar'
          }
        </button>
      `
      : '';

    return `
      <article
        class="health-panel health-google"
      >
        <div class="health-google-head">
          <div>
            <h3>Google Calendar</h3>

            <span
              class="health-google-state ${
                connected
                  ? 'is-ok'
                  : 'is-off'
              }"
            >
              ${esc(stateText)}
            </span>
          </div>

          ${action}
        </div>

        <p>${detail}</p>

        <small>
          OAuth callback:
          ${esc(status.redirect_uri||'')}
        </small>

        <div id="googleCalendarResult"></div>
      </article>
    `;
  }

  async function connectGoogle(){
    const button=
      document.querySelector(
        '#googleCalendarConnect'
      );

    const result=
      document.querySelector(
        '#googleCalendarResult'
      );

    if(button){
      button.disabled=true;
    }

    if(result){
      result.innerHTML=
        '<div class="health-note">Открываю Google…</div>';
    }

    try{
      const data=await readJson(
        '/api/teacher/google-calendar/connect',
        {
          method:'POST',
          headers:{
            'Content-Type':
              'application/json'
          },
          body:'{}'
        }
      );

      if(!data.authorization_url){
        throw new Error(
          'authorization_url_missing'
        );
      }

      window.location.href=
        data.authorization_url;

    }catch(error){

      if(result){
        result.innerHTML=`
          <div class="health-warning">
            Не удалось начать подключение:
            ${esc(error.message)}
          </div>
        `;
      }

      if(button){
        button.disabled=false;
      }
    }
  }

  async function load(){
    const app=
      document.querySelector('#app');

    const title=
      document.querySelector('#title');

    if(!app){
      return;
    }

    if(title){
      title.textContent=
        'Состояние Аделии';
    }

    app.innerHTML=
      '<section class="health-loading">Проверяю состояние Аделии…</section>';

    try{
      const [
        health,
        google
      ]=await Promise.all([
        readJson(
          '/api/teacher/server-health'
        ),

        readJson(
          '/api/teacher/google-calendar/status'
        ).catch(()=>null)
      ]);

      const disk=
        health.disk||{};

      const memory=
        health.memory||{};

      const storage=
        health.storage||{};

      const warnings=
        Array.isArray(health.warnings)
          ? health.warnings
          : [];

      const storageRows=
        Object.entries(storage)
          .map(
            ([key,value])=>`
              <div class="health-storage-row">
                <span>
                  ${esc(value.label||key)}
                </span>

                <b>
                  ${
                    bytes(
                      value.bytes
                      ?? value.size_bytes
                      ?? value
                    )
                  }
                </b>
              </div>
            `
          )
          .join('');

      app.innerHTML=`
        ${oauthNotice()}

        <section class="health-hero">
          <div>
            <span class="health-kicker">
              Системный контроль
            </span>

            <h2>
              ${
                warnings.length
                  ? 'Нужно внимание'
                  : 'Аделия работает штатно'
              }
            </h2>

            <p>
              Только служебная информация сервера.
              Удаление файлов с этого экрана
              не выполняется.
            </p>
          </div>

          <button
            class="soft"
            id="healthRefresh"
          >
            Обновить
          </button>
        </section>

        <section class="health-grid">
          <article class="health-card">
            <span>Диск</span>

            <strong>
              ${
                disk.used_percent
                ?? disk.percent
                ?? '—'
              }%
            </strong>

            <small>
              ${
                bytes(
                  disk.free_bytes
                  ?? disk.free
                )
              }
              свободно
            </small>
          </article>

          <article class="health-card">
            <span>
              Оперативная память
            </span>

            <strong>
              ${
                memory.used_percent
                ?? memory.percent
                ?? '—'
              }%
            </strong>

            <small>
              ${
                bytes(
                  memory.available_bytes
                  ?? memory.available
                )
              }
              доступно
            </small>
          </article>

          <article class="health-card">
            <span>База данных</span>

            <strong>
              ${
                bytes(
                  health.database?.bytes
                  ?? health.database_bytes
                )
              }
            </strong>

            <small>
              Основные данные Аделии
            </small>
          </article>

          <article class="health-card">
            <span>Статус</span>

            <strong>
              ${
                warnings.length
                  ? warnings.length
                  : 'OK'
              }
            </strong>

            <small>
              ${
                warnings.length
                  ? 'предупреждений'
                  : 'критичных предупреждений нет'
              }
            </small>
          </article>
        </section>

        ${googlePanel(google)}

        <section class="health-columns">
          <article class="health-panel">
            <h3>Хранилище</h3>

            ${
              storageRows
              || `
                <div class="health-empty">
                  Детализация хранилища
                  пока недоступна.
                </div>
              `
            }
          </article>

          <article class="health-panel">
            <h3>Предупреждения</h3>

            ${
              warnings.length
                ? warnings
                    .map(
                      warning=>`
                        <div class="health-warning">
                          ${
                            esc(
                              warning.message
                              || warning
                            )
                          }
                        </div>
                      `
                    )
                    .join('')
                : `
                  <div class="health-ok">
                    ✓ Всё в пределах нормы
                  </div>
                `
            }

            <div class="health-note">
              Безопасная оптимизация появится
              отдельным действием
              с предварительным просмотром.
              База, чеки, материалы учеников
              и конфигурация будут защищены
              от удаления.
            </div>
          </article>
        </section>
      `;

      document
        .querySelector('#healthRefresh')
        ?.addEventListener(
          'click',
          load
        );

      document
        .querySelector(
          '#googleCalendarConnect'
        )
        ?.addEventListener(
          'click',
          connectGoogle
        );

      const params=
        new URLSearchParams(
          window.location.search
        );

      if(params.has('google')){
        window.history.replaceState(
          {},
          '',
          window.location.pathname
          + window.location.hash
        );
      }

    }catch(error){

      app.innerHTML=`
        <section class="health-error">
          <b>
            Не удалось проверить сервер
          </b>

          <span>
            ${esc(error.message)}
          </span>

          <button
            class="soft"
            id="healthRetry"
          >
            Повторить
          </button>
        </section>
      `;

      document
        .querySelector('#healthRetry')
        ?.addEventListener(
          'click',
          load
        );
    }
  }

  const original=
    window.show;

  if(typeof original==='function'){
    window.show=
      async function(view){

        if(view==='health'){
          document
            .querySelectorAll(
              'nav button'
            )
            .forEach(
              button=>
                button.classList.toggle(
                  'active',
                  button.dataset.view
                    ==='health'
                )
            );

          return load();
        }

        return original.apply(
          this,
          arguments
        );
      };
  }

  document.addEventListener(
    'click',
    event=>{
      const button=
        event.target.closest(
          '[data-view="health"]'
        );

      if(!button){
        return;
      }

      event.preventDefault();

      load();
    }
  );
})();
