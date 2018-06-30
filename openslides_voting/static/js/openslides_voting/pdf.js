(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.pdf', ['OpenSlidesApp.core.pdf'])

.factory('MotionPollContentProvider', [
    'gettextCatalog',
    'MotionPollBallot',
    'PDFLayout',
    function(gettextCatalog, MotionPollBallot, PDFLayout) {
        var createInstance = function(motion, poll, ballots, pollType) {

            // Title
            var pdfTitle = PDFLayout.createTitle(motion.getTitle() + ' - ' +
                gettextCatalog.getString('Single votes'));

            // Subtitle
            var i = _.findIndex(motion.polls, function (p) { return p.id == poll.id;  });
            var pdfSubtitle = PDFLayout.createSubtitle([ (i + 1) + '. ' + gettextCatalog.getString('Vote')]);

            // TODO: Add vote result table. See MotionContentProvider.

            // Create single votes table. Order by user fullname.
            var voteStr = {Y: 'Yes', N: 'No', A: 'Abstain'};

            var tableBody = [
                [
                    {
                        text: (pollType === 'token_based_electronic'
                            ? gettextCatalog.getString('Result token')
                            : gettextCatalog.getString('Delegate')),
                        style: 'tableHeader'
                    },
                    {
                        text: gettextCatalog.getString('Vote'),
                        style: 'tableHeader'
                    }
                ]
            ];
            _.forEach(ballots, function (ballot, index) {
                var username = ballot.user ? ballot.user.full_name : gettextCatalog.getString('anonym');
                tableBody.push([
                    {
                        text: (pollType === 'token_based_electronic'
                            ? ballot.result_token
                            : username),
                        style: PDFLayout.flipTableRowStyle(index),
                    },
                    {
                        text: gettextCatalog.getString(voteStr[ballot.vote]),
                        style: PDFLayout.flipTableRowStyle(index),
                    }
                ]);
            });

            var pdfTable = {
                table: {
                    widths: ['*', '*'],
                    headerRows: 1,
                    body: tableBody
                },
                layout: 'headerLineOnly',
            };

            return {
                getContent: function () {
                    return [
                        pdfTitle,
                        pdfSubtitle,
                        pdfTable
                    ];
                },
            };
        };

        return {
            createInstance: createInstance,
        };
    }
])

.factory('AttendanceHistoryContentProvider', [
    '$filter',
    'gettextCatalog',
    'VotingPrinciple',
    'AttendanceLog',
    'PDFLayout',
    function ($filter, gettextCatalog, VotingPrinciple, AttendanceLog, PDFLayout) {
        var createInstance = function () {

             // Title
            var pdfTitle = PDFLayout.createTitle(gettextCatalog.getString('Attendance history'));

            // Create attendance history table. Order by descending created time.

            // Create table columns. Header: 'Time', 'Heads', voting principles.
            var principles = VotingPrinciple.filter({orderBy: 'id'});
            var columns = [
                [gettextCatalog.getString('Time')],
                [gettextCatalog.getString('Heads')]
            ];
            _.forEach(principles, function (principle) {
                columns.push([principle.name]);
            });

            // Create table data.
            _.forEach(AttendanceLog.filter({orderBy: ['created', 'DESC']}), function (log) {
                // TODO: Use localized time format.
                columns[0].push($filter('date')(log.created, 'yyyy-MM-dd HH:mm:ss'));
                columns[1].push($filter('number')(log.json().heads, 0));
                _.forEach(principles, function (principle, index) {
                    columns[index + 2].push(
                        $filter('number')(log.json()[principle.id], principle.decimal_places)
                    );
                });
            });

            var tableBody = [[{
                columns: [],
                columnGap: 10,
            }]];
            _.forEach(columns, function (column, index) {
                tableBody[0][0].columns.push({
                    text: column.join('\n'),
                    width: 'auto',
                    alignment: (index > 0) ? 'right' : 'left'
                });
            });

            var pdfTable = {
                table: {
                    body: tableBody,
                    widths: ['auto']
                },
                // TODO: Replace layout placeholder with static values for LineWidth and LineColor.
                layout: '{{motion-placeholder-to-insert-functions-here}}'
            };

            return {
                getContent: function () {
                    return [
                        pdfTitle,
                        pdfTable
                    ];
                }
            };
        };

        return {
            createInstance: createInstance,
        };
    }
])

.factory('Barcode', [
    function () {
        return {
            getBase64: function (text, options) {
                options = options || {};
                var canvas = document.createElement('canvas');
                JsBarcode(canvas, text, options);
                return canvas.toDataURL();
            },
        };
    }
])

.factory('TokenContentProvider', [
    'PDFLayout',
    'Barcode',
    'gettextCatalog',
    function (PDFLayout, Barcode, gettextCatalog) {
        var createInstance = function (tokens) {

            var tokenTables = function () {
                var tokensPerPage = 8; // This needs to be fitted to the dimensions of
                // the barcode below. If there are more barcodes then a page can
                // take, the text will be shifted up or down, because pagebreaks
                // in the columns are different.
                var tables = [];
                var currentTableBody;
                _.forEach(tokens, function (token, index) {
                    if ((index % (tokensPerPage+1)) === 0) {
                        if (currentTableBody) {
                            tables.push({
                                table: {
                                    widths: ['*', '*'],
                                    headerRows: 1,
                                    body: currentTableBody,
                                },
                                layout: 'noBorders',
                            });
                            tables.push({
                                text: '',
                                pageBreak: 'after',
                            });
                        }
                        // An empty table head
                        currentTableBody = [
                            [
                                {
                                    text: '',
                                },
                                {
                                    text: '',
                                }
                            ]
                        ];
                    } else {
                        currentTableBody.push([
                            {
                                text: token,
                                fontSize: 16,
                                margin: [50, 35, 0, 0], // left, top, right, bottom
                            },
                            {
                                image: Barcode.getBase64(token, {
                                    fontSize: 10,
                                    height: 50,
                                    width: 1,
                                    text: ' ',
                                }),
                                margin: [0, 10, 0, 0],
                            }
                        ]);
                    }
                });
                if (currentTableBody.length > 1) {
                    tables.push({
                        table: {
                            widths: ['*', '*'],
                            headerRows: 1,
                            body: currentTableBody,
                        },
                        layout: 'noBorders',
                    });
                }

                return tables;
            };

            return {
                getContent: function () {
                    return tokenTables();
                },
            };
        };

        return {
            createInstance: createInstance,
        };
    }
])

.factory('TokenDocumentProvider', [
    function () {
        var createInstance = function(contentProvider) {
            var getDocument = function() {
                var content = contentProvider.getContent();
                return {
                    pageSize: 'A4',
                    pageMargins: [10, 10, 10, 10],
                    defaultStyle: {
                        font: 'PdfFont',
                        fontSize: 10
                    },
                    content: content,
                };
            };

            return {
                getDocument: getDocument,
                getImageMap: function () {
                    return {};
                },
            };
        };
        return {
            createInstance: createInstance
        };
    }
]);

}());
