(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.pdf', ['OpenSlidesApp.core.pdf'])

.factory('MotionPollContentProvider', [
    'gettextCatalog',
    'MotionPollBallot',
    'PDFLayout',
    function(gettextCatalog, MotionPollBallot, PDFLayout) {
        var createInstance = function(motion, poll) {

            // Title
            var pdfTitle = PDFLayout.createTitle(motion.getTitle() + ' - ' +
                gettextCatalog.getString('Single votes'));

            // Subtitle
            var i = _.findIndex(motion.polls, function (p) { return p.id == poll.id;  });
            var pdfSubtitle = PDFLayout.createSubtitle([ i + 1 + '. ' + gettextCatalog.getString('Vote')]);

            // TODO: Add vote result table. See MotionContentProvider.

            // Create single votes table. Order by user fullname.
            var ballots = MotionPollBallot.filter({poll_id: poll.id, orderBy: 'user.full_name'}),
                voteStr = {Y: 'Yes', N: 'No', A: 'Abstain'},
                tableBody = [],
                column1 = [],
                column2 = [],
                column3 = [];
            _.forEach(ballots, function (ballot, index) {
                column1.push(index + 1 + '.');
                column2.push(ballot.user.full_name);
                column3.push(gettextCatalog.getString(voteStr[ballot.vote]));
            });

            tableBody.push([
                {
                    columns: [
                        {
                            text: column1.join('\n'),
                            width: 'auto',
                            alignment: 'right'
                        },
                        {
                            text: column2.join('\n'),
                            width: 'auto'
                        },
                        {
                            text: column3.join('\n'),
                            width: 'auto'
                        }
                        // TODO: Add voting shares column
                    ],
                    columnGap: 10
                    // style: 'grey'
                }
            ]);

            var pdfTable = {
                table: {
                    body: tableBody
                },
                // TODO: Replace layout placeholder with static values for LineWidth and LineColor.
                layout: '{{motion-placeholder-to-insert-functions-here}}'
            };

            return {
                getContent: function () {
                    return [
                        pdfTitle,
                        pdfSubtitle,
                        pdfTable
                    ]
                }
            };
        };

        return {
            createInstance: createInstance
        };
    }
])

.factory('AttendanceHistoryContentProvider', [
    '$filter',
    'gettextCatalog',
    'Category',
    'VotingPrinciple',
    'AttendanceLog',
    'PDFLayout',
    function ($filter, gettextCatalog, Category, VotingPrinciple, AttendanceLog, PDFLayout) {
        var createInstance = function () {

             // Title
            var pdfTitle = PDFLayout.createTitle(gettextCatalog.getString('Attendance history'));

            // Create attendance history table. Order by descending created time.

            // Create table columns. Header: 'Time', 'Heads', voting principles (category names).
            var categories = Category.filter({orderBy: 'id'});
            var columns = [
                [gettextCatalog.getString('Time')],
                [gettextCatalog.getString('Heads')]
            ];
            _.forEach(categories, function (cat) {
                columns.push([cat.name]);
            });

            // Create table data.
            _.forEach(AttendanceLog.filter({orderBy: ['created', 'DESC']}), function (log) {
                // TODO: Use localized time format.
                columns[0].push($filter('date')(log.created, 'yyyy-MM-dd HH:mm:ss'));
                columns[1].push($filter('number')(log.json()['heads'], 0));
                _.forEach(categories, function (cat, index) {
                    var precision = VotingPrinciple.getPrecision(cat.name);
                    columns[index + 2].push($filter('number')(log.json()[cat.id], precision));
                });
            });

            var tableBody = [[{
                columns: [],
                columnGap: 10
            }]];
            _.forEach(columns, function (column, index) {
                tableBody[0][0].columns.push({
                    text: column.join('\n'),
                    width: 'auto',
                    alignment: (index > 0) ? 'right' : 'left'
                })
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
                    ]
                }
            };
        };

        return {
            createInstance: createInstance
        };
    }
])

}());
