$(document).ready(function () {
    $('[id$="_table"]').each(function () {
        var table = $(this).DataTable({
            scrollX: true,
            "pageLength": 25,
            aaSorting: [],
            columnDefs: [
                { targets: "_all", className: "dt-left dt-body-left display dt-no-padding" },
                { type: "string", targets: 0 }
            ],
            "oLanguage": {
                "sSearch": "",
                "sSearchPlaceholder": "Filter Results",
                "sLengthMenu": "_MENU_ &nbsp;per page",
            },
            "createdRow": function (row, data, dataIndex) {
                var table = $(this).DataTable();
                var tableId = table.settings()[0].sTableId;
                var rawTable = document.getElementById(tableId);
                var headersRow = rawTable.rows[0];
                var headerCells = headersRow.cells;
                var columnName = headerCells[data.length-1].innerText;
                if (columnName === "...") {}
                var color = '';
                $(row).css('background-color', color); 
                $(row).css('background-opacity', 0.5); 
            },
            layout: {
                top1Start: {
                    search: {
                    },
                    pageLength: {
                        menu: [10, 25, 50, 100, 200, 1000]
                    },
                    buttons: [
                        'copyHtml5',
                        'excelHtml5',
                        'csvHtml5',
                        'pdfHtml5',
                    ],
                },
                top1End: null,
                topStart: 'info',
                topEnd: 'paging',
                bottomStart: 'info',
                bottomEnd: 'paging'
            },
            "initComplete": function () {
                var api = this.api();
                var table = api.table(); // Current table
                var btns = $(table.table().container()).find('.dt-button');
                btns.addClass('bi');
                var icon_map = {
                    "PDF": "bi-filetype-pdf",
                    "CSV": "bi-filetype-csv",
                    "Excel":"bi-file-earmark-spreadsheet",
                    "Copy": "bi-copy",
                }

                btns.each(function () {
                    var buttonText = $(this).text().trim();
                    $(this).addClass(icon_map[buttonText]);
                });
                

                btns.addClass('datatables-export text-muted');

                btns.each(function() {
                    $(this).find('span').prepend('&nbsp;');
                });

                var mutedColor = getComputedColor('text-primary');
                var filterInput = $(api.table().container()).find('.dt-input input');
                filterInput.css('color', mutedColor);

                $(table.table().container()).find('.dt-info').addClass("text-normal");
                $(table.table().container()).find('.dt-length').find("label").addClass("text-normal");
                $(api.table().header()).find('th').addClass('bg-dark text-light');

                var primarycolor = getComputedColor('text-light');
                // Dynamically inject CSS to set placeholder color
                var style = document.createElement('style');
                style.innerHTML = '.dt-column-search-input::placeholder { color: ' + primarycolor + '; }';
                document.getElementsByTagName('head')[0].appendChild(style);

                $(api.table().header()).find('th').each(function (index) {
                    var column = table.column(index);
                    var title = $(this).text();
                    $(this).html(
                        '<input type="text" class="dt-column-search-input bg-transparent mx-0 my-0 text-light" placeholder="'
                        + title + '" /><span class="dt-column-title" role="button" style="display:none;">' + title
                        + '</span><span class="dt-column-order" style="right:0px;top:-4px;"></span>'
                    );
                    $('input', this).on('click', function (e) {
                        e.stopPropagation(); // Prevent propagation to avoid sorting
                    });
                    $('input', this).on('keyup change', function () {
                        if (column.search() !== this.value) {
                            column.search(this.value).draw();
                        }
                    });
                });
                $(api.table().header()).find('th').on('click', function (e) {
                    e.preventDefault(); 
                });

            }
        });
        new $.fn.dataTable.FixedHeader(table);
    });
});