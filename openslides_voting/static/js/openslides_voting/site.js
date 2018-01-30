(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.site', [
    'OpenSlidesApp.openslides_voting',
    'OpenSlidesApp.openslides_voting.voting',
    'OpenSlidesApp.openslides_voting.pdf'
])

.config([
    'mainMenuProvider',
    'gettext',
    function (mainMenuProvider, gettext) {
        mainMenuProvider.register({
            'ui_sref': 'openslides_voting.delegate.list',
            'img_class': 'thumbs-o-up',
            'title': 'Delegates',
            'weight': 510,
            'perm': 'openslides_voting.can_manage'
        });
    }
])

.config([
    '$stateProvider',
    function ($stateProvider) {
        $stateProvider
        .state('openslides_voting', {
            url: '/voting',
            abstract: true,
            template: "<ui-view/>"
        })
        .state('openslides_voting.delegate', {
            abstract: true,
            template: "<ui-view/>"
        })
        .state('openslides_voting.delegate.list', {
        })
        .state('openslides_voting.delegate.import', {
            url: '/import',
            controller: 'VotingShareImportCtrl'
        })
        .state('openslides_voting.delegate.attendance', {
            url: '/attendance',
            controller: 'DelegateAttendanceCtrl'
        })
        .state('openslides_voting.keypad', {
            url: '/keypad',
            abstract: true,
            template: "<ui-view/>"
        })
        .state('openslides_voting.keypad.list', {})
        .state('openslides_voting.keypad.import', {
            url: '/import',
            controller: 'KeypadImportCtrl'
        })
        .state('openslides_voting.absenteeVote', {
            url: '/absenteevote',
            abstract: true,
            template: "<ui-view/>"
        })
        .state('openslides_voting.absenteeVote.list', {})
        .state('openslides_voting.absenteeVote.import', {
            url: '/import',
            controller: 'AbsenteeVoteImportCtrl'
        })
        .state('openslides_voting.motionPoll', {
            abstract: true,
            template: "<ui-view/>"
        })
        .state('openslides_voting.motionPoll.detail', {
            url: '/motionpoll/:id',
            controller: 'MotionPollVoteDetailCtrl'
        })
    }
])
    
.factory('DelegateForm', [
    'gettextCatalog',
    'Category',
    'VotingPrinciple',
    'User',
    function (gettextCatalog, Category, VotingPrinciple, User) {
        return {
            getDialog: function (delegate) {
                return {
                    template: 'static/templates/openslides_voting/delegate-form.html',
                    controller: 'DelegateUpdateCtrl',
                    className: 'ngdialog-theme-default wide-form',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: {
                        delegate: function () {
                            return delegate;
                        }
                    }
                }
            },
            getFormFields: function (delegate) {
                var otherDelegates = User.filter({
                        where: {
                            id: {
                                '!=': delegate.user.id
                            },
                            groups_id : 2
                        },
                        orderBy: 'full_name'
                    });
                var formFields = [
                {
                    key: 'keypad_number',
                    type: 'input',
                    templateOptions: {
                        label: gettextCatalog.getString('Keypad'),
                        type: 'number'
                    },
                    watcher: {
                        listener: function (field, newValue, oldValue, formScope) {
                            if (newValue) {
                                formScope.model.proxy_id = null;
                                formScope.options.formState.notRegistered = false;
                            }
                            else {
                                formScope.model.is_present = false;
                                formScope.options.formState.notRegistered = true;
                            }
                        }
                    }
                },
                {
                    key: 'is_present',
                    type: 'checkbox',
                    templateOptions: {
                        label: gettextCatalog.getString('Present')
                    },
                    expressionProperties: {
                        'templateOptions.disabled': 'formState.notRegistered'
                    }
                },
                {
                    key: 'proxy_id',
                    type: 'select-single',
                    templateOptions: {
                        label: gettextCatalog.getString('Proxy'),
                        options: otherDelegates,
                        ngOptions: 'option.id as option.full_name for option in to.options',
                        placeholder: '(' + gettextCatalog.getString('No proxy') + ')'
                    },
                    watcher: {
                        listener: function (field, newValue, oldValue, formScope) {
                            if (newValue) {
                                formScope.model.keypad_number = null;
                            }
                        }
                    }
                },
                {
                    key: 'mandates_id',
                    type: 'select-multiple',
                    templateOptions: {
                        label: gettextCatalog.getString('Principals'),
                        options: otherDelegates,
                        ngOptions: 'option.id as option.full_name for option in to.options',
                        placeholder: '(' + gettextCatalog.getString('No principals') + ')'
                    }
                },
                {
                    key: 'more',
                    type: 'checkbox',
                    templateOptions: {
                        label: gettextCatalog.getString('Show voting rights')
                    }
                },
                {
                    template: '<hr class="smallhr">',
                    hideExpression: '!model.more'
                }
                ];

                var fieldGroup = [];
                _.forEach(Category.filter({orderBy: 'id'}), function (cat) {
                    fieldGroup.push({
                        key: 'shares[' + cat.id + ']',
                        type: 'input',
                        className: "col-xs-2 no-padding-left",
                        templateOptions: {
                            label: cat.name,
                            type: 'number',
                            step: VotingPrinciple.getStep(cat.name)
                        }
                    });
                    if (fieldGroup.length == 6) {
                        formFields.push({
                            className: "row",
                            fieldGroup: fieldGroup,
                            hideExpression: '!model.more'
                        });
                        fieldGroup = [];
                    }
                });
                if (fieldGroup.length > 0) {
                    // TODO: Find a better way to deal with last col-xs.
                    var n = (6 - fieldGroup.length) * 2 + 2 ;
                    _.last(fieldGroup).className = "no-padding-left col-xs-" + n;
                    formFields.push({
                        className: "row",
                        fieldGroup: fieldGroup,
                        hideExpression: '!model.more'
                    });
                }
                return formFields;
            }
        };
    }
])
    
.controller('DelegateListCtrl', [
    '$scope',
    '$timeout',
    'ngDialog',
    'DelegateForm',
    'Delegate',
    'User',
    'Keypad',
    'VotingProxy',
    'VotingShare',
    'Category',
    'VotingPrinciple',
    function ($scope, $timeout, ngDialog, DelegateForm, Delegate, User, Keypad, VotingProxy, VotingShare,
              Category, VotingPrinciple) {
        Category.bindAll({}, $scope, 'categories');
        $scope.alert = {};

        var updatePromise;
        var updateListView = function () {
            // console.log('Start updating')
            var delegates = [];
            // TODO: Allow a delegate to belong to another group besides group 2.
            _.forEach(User.filter({groups_id: 2}), function (user) {
                var d = {user: user};
                d.keypad = Delegate.getKeypad(user.id);
                d.proxy = Delegate.getProxy(user.id );
                d.shares = Delegate.getShares(user.id);
                d.status = Delegate.getStatus(d);
                delegates.push(d);
                console.log('Updating delegate');
            });
            $scope.delegates = delegates;

            // Count attending, represented and absent delegates.
            $scope.attendingCount = Keypad.filter({ 'user.is_present': true }).length;
            $scope.representedCount = VotingProxy.getAll().length;
            $scope.absentCount = Math.max(0,
                $scope.delegates.length - $scope.attendingCount - $scope.representedCount);

            // console.log('Updated list view');
            return $scope.delegates.length;
        };

        $scope.$watch(function () {
            // No need to watch User or Keypad. Template variables .user and .keypad update automatically.
            return VotingProxy.lastModified() + VotingShare.lastModified();
        }, function () {
            // NOTE: This function will execute the first time when controller is initiated.
            var t = 0;
            if (updatePromise) {
                // Reschedule to only update list view once after all modifications have been received.
                $timeout.cancel(updatePromise);
                t = 1000;
            }
            updatePromise = $timeout(updateListView, t);
            console.log('Reschedule list view update');
        });

        $scope.$on('$destroy', function () {
            $timeout.cancel(updatePromise);
        });

        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 20,  // NOTE: Less records on page will speed up loading the edit form.
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Handle table column sorting.
        $scope.sortColumn = 'user.full_name';
        $scope.reverse = false;
        $scope.toggleSort = function (column) {
            if ( $scope.sortColumn === column ) {
                $scope.reverse = !$scope.reverse;
            }
            $scope.sortColumn = column;
        };

        // Define custom search filter string.
        $scope.getFilterString = function (delegate) {
            var rep = '', keypad = '';
            if (delegate.proxy) {
                rep = delegate.proxy.rep.full_name;
            }
            if (delegate.keypad) {
                keypad = delegate.keypad.number;
            }
            return [
                delegate.user.full_name,
                rep,
                keypad
            ].join(' ');
        };

        $scope.getVPName = VotingPrinciple.getName;
        $scope.getVPPrecision = VotingPrinciple.getPrecision;

        // Open edit dialog.
        $scope.openDialog = function (delegate) {
            ngDialog.open(DelegateForm.getDialog(delegate));
        };
    }
])

.controller('DelegateUpdateCtrl', [
    '$scope',
    '$q',
    '$http',
    'DelegateForm',
    'Delegate',
    'User',
    'Category',
    'delegate',
    function ($scope, $q, $http, DelegateForm, Delegate, User, Category, delegate) {
        var message,
            onFailed = function (error) {
                for (var e in error.data) {
                    message += e + ': ' + error.data[e] + ' ';
                }
            };

        $scope.model = angular.copy(delegate);
        $scope.model.keypad_number = delegate.keypad ? delegate.keypad.number : null;
        $scope.model.is_present = delegate.user.is_present;
        $scope.model.proxy_id = delegate.proxy ? delegate.proxy.proxy_id : null;
        $scope.model.mandates_id = Delegate.getMandates(delegate.user.id).map(function (vp) { return vp.delegate_id });

        $scope.formFields = DelegateForm.getFormFields($scope.model);

        $scope.save = function (delegate) {
            message = '';
            $scope.alert = {};

            // Check for circular proxy reference.
            if (delegate.mandates_id.indexOf(delegate.proxy_id) >= 0) {
                message = User.get(delegate.proxy_id).full_name +
                    ' kann nicht gleichzeitig Vertreter und Vollmachtgeber sein.'
                $scope.alert = {type: 'danger', msg: message, show: true};
                return;
            }

            // Update keypad, proxy, mandates, voting shares, user.is_present and collect their promises.
            var promises = [];
            Delegate.updateKeypad(delegate, delegate.keypad_number, promises, onFailed);
            Delegate.updateProxy(delegate, delegate.proxy_id, promises);
            Delegate.updateMandates(delegate, promises);
            Delegate.updateShares(delegate, promises);
            if (delegate.user.is_present != delegate.is_present) {
                var user = User.get(delegate.user.id);
                user.is_present = delegate.is_present;
                promises.push(User.save(user));
            }

            // Wait until all promises have been resolved before closing dialog.
            $q.all(promises).then(function () {
                if (message) {
                    $scope.alert = {type: 'danger', msg: message, show: true};
                }
                else {
                    $scope.closeThisDialog();

                    // Get an attendance update.
                    // The server will create an attendance log entry if attendance
                    // has changed due to keypad, proxy, user present updates issued above.
                    $http.get('/voting/attendance/shares/');
                }
            });
        };
    }
])

.controller('DelegateAttendanceCtrl', [
    '$scope',
    '$http',
    '$interval',
    'gettextCatalog',
    'Category',
    'VotingPrinciple',
    'AttendanceLog',
    'AttendanceHistoryContentProvider',
    'PdfMakeDocumentProvider',
    'PdfCreate',
    function ($scope, $http, $interval, gettextCatalog, Category, VotingPrinciple,
              AttendanceLog, AttendanceHistoryContentProvider,
              PdfMakeDocumentProvider, PdfCreate) {
        Category.bindAll({}, $scope, 'categories');
        AttendanceLog.bindAll({}, $scope, 'attendanceLogs');

        $scope.historyVisible = false;

        var updateAttendance = function () {
            // Get attendance data from server.
            $http.get('/voting/attendance/shares/').then(function (success) {
                console.log('Updating attendance view');
                $scope.attendance = success.data;
            });
        };

        // Update attendance view whenever attendance logs or voting principles, i.e. categories have changed.
        $scope.$watch(function () {
            return AttendanceLog.lastModified() + Category.lastModified();
        }, updateAttendance);

        $scope.getVPName = VotingPrinciple.getName;
        $scope.getVPPrecision = VotingPrinciple.getPrecision;

        // Delete all attendance logs.
        $scope.deleteHistory = function () {
            // NOTE: AttendanceLog.destroyAll() is not allowed. Not sure why.
            // TODO: Prevent redundant updateAttendance calls for each log deleted.
            _.forEach(AttendanceLog.getAll(), function (log) {
                AttendanceLog.destroy(log.id);
            });
        };

        // PDF export
        $scope.pdfExport = function () {
            var filename = gettextCatalog.getString('AttendanceHistory') + '.pdf';
            var contentProvider = AttendanceHistoryContentProvider.createInstance();
            var documentProvider = PdfMakeDocumentProvider.createInstance(contentProvider);
            var document = documentProvider.getDocument();
            // Use landscape orientation to fit more voting principles on page.
            // TODO: PDF paper cuts off after about 10 columns.
            document.pageOrientation = 'landscape';
            PdfCreate.download(document, filename);
        };
    }
])

.controller('VotingShareImportCtrl', [
    '$scope',
    '$q',
    'gettext',
    'VotingShare',
    'User',
    'Category',
    function ($scope, $q, gettext, VotingShare, User, Category) {
        // Set up pagination.
        $scope.pg = {
            firstItem: 0,
            currentPage: 1,
            itemsPerPage: 100,
            pageChanged: function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Configure csv.
        var fields = [];
        $scope.categories = [];
        $scope.delegateShares = [];
        $scope.csvConfig = {
            accept: '.csv, .txt',
            encodingOptions: ['UTF-8', 'ISO-8859-1'],
            parseConfig: {
                skipEmptyLines: true
            }
        };

        // Load csv file.
        $scope.onCsvChange = function (csv) {
            var records = [],
                users = User.getAll();

            $scope.clear();

            // Get voting principles (categories) and fields from header row.
            if (csv.meta !== undefined) {
                $scope.categories = csv.meta.fields.splice(3);
            }

            // Define field names.
            fields = ['first_name', 'last_name', 'number'].concat($scope.categories);

            // Read csv rows.
            _.forEach(csv.data, function (row) {
                if (row.length >= 4) {
                    var filledRow = _.zipObject(fields, row);
                    records.push(filledRow);
                }
            });
            // Validate each record.
            _.forEach(records, function (record) {
                record.selected = true;
                if (record.first_name == '' && record.last_name == '') {
                    // User is anonymous.
                    record.user_id = null;
                }
                else {
                    // Find user.
                    record.error = {};
                    record.fullname = [record.first_name, record.last_name, record.number].join(' ');
                    var user = _.find(users, function (item) {
                        item.fullname = [item.first_name, item.last_name, item.number].join(' ');
                        return item.fullname == record.fullname;
                    });
                    if (user != undefined) {
                        record.user_id = user.id;
                        record.fullname = user.get_full_name();
                    }
                    else {
                        record.user_id = -1;
                        record.importerror = true;
                        record.error.user = gettext('Error: Participant not found.');
                    }
                }
                // Validate voting shares.
                _.forEach($scope.categories, function (cat) {
                    var num = parseFloat(record[cat]);
                    if (isNaN(num) || num < 0) {
                        record.importerror = true;
                        record.error[cat] = gettext('Error: Not a valid number.')
                    }
                    else {
                        record[cat] = num;
                    }
                });
                $scope.delegateShares.push(record);
            });
            $scope.calcStats();
        };

        $scope.calcStats = function () {
            $scope.sharesWillNotBeImported = 0;
            $scope.sharesWillBeImported = 0;

            $scope.delegateShares.forEach(function (item) {
                if (!item.importerror && item.selected) {
                    $scope.sharesWillBeImported++;
                } else {
                    $scope.sharesWillNotBeImported++;
                }
            });
        };

        // Import voting shares.
        $scope.import = function () {
            var categories = {},
                promises = [];
            $scope.csvImporting = true;

            // Create categories.
            _.forEach($scope.categories, function (cat) {
                var cats = Category.filter({name: cat});
                if (cats.length >= 1) {  // TODO: Handle duplicate category name.
                    categories[cat] = cats[0].id;
                }
                else {
                    promises.push(Category.create({name: cat}).then(
                        function (success) {
                            categories[success.name] = success.id;
                        }
                    ));
                }
            });

            $q.all(promises).then(function () {
                angular.forEach($scope.delegateShares, function (delegateShare) {
                    if (delegateShare.selected && !delegateShare.importerror) {
                        _.forEach($scope.categories, function (cat) {
                            // Look for an existing voting share.
                            var vss = VotingShare.filter({
                                delegate_id: delegateShare.user_id,
                                category_id: categories[cat]
                            });
                            if (vss.length == 1) {
                                // Update voting share.
                                vss[0].shares = delegateShare[cat];
                                VotingShare.save(vss[0]).then(function (success) {
                                    delegateShare.imported = true;
                                });
                            }
                            else {
                                // Create voting share.
                                VotingShare.create({
                                    delegate_id: delegateShare.user_id,
                                    category_id: categories[cat],
                                    shares: delegateShare[cat]
                                }).then(function (success) {
                                    delegateShare.imported = true;
                                });
                            }
                        });
                    }
                });
            });
            $scope.csvImported = true;
        };

        // Clear csv import preview.
        $scope.clear = function () {
            $scope.delegateShares = [];
            $scope.csvImporting = false;
            $scope.csvImported = false;
        };
    }
])

.controller('MotionPollVoteDetailCtrl', [
    '$scope',
    '$stateParams',
    'gettextCatalog',
    'Motion',
    'MotionPoll',
    'MotionPollBallot',
    'MotionPollContentProvider',
    'PdfMakeDocumentProvider',
    'PdfCreate',
    function ($scope, $stateParams, gettextCatalog, Motion, MotionPoll, MotionPollBallot, MotionPollContentProvider,
                PdfMakeDocumentProvider, PdfCreate) {
        var pollId = $stateParams.id;
        var motion = MotionPoll.get(pollId).motion;
        Motion.bindOne(motion.id, $scope, 'motion');
        MotionPoll.bindOne(pollId, $scope, 'poll');
        MotionPollBallot.bindAll({poll_id: pollId}, $scope, 'ballots');

        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 50,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Handle table column sorting.
        $scope.sortColumn = 'user.full_name';
        $scope.reverse = false;
        $scope.toggleSort = function (column) {
            if ( $scope.sortColumn === column ) {
                $scope.reverse = !$scope.reverse;
            }
            $scope.sortColumn = column;
        };

        // Define custom search filter string.
        $scope.getFilterString = function (ballot) {
            return [
                ballot.user.full_name,
                ballot.getVote()
            ].join(' ');
        };

        // PDF export
        $scope.pdfExport = function () {
            var filename = gettextCatalog.getString('Motion') + '-' + motion.identifier + '-' +
                gettextCatalog.getString('SingleVotes') + '.pdf';
            var contentProvider = MotionPollContentProvider.createInstance(motion, $scope.poll);
            var documentProvider = PdfMakeDocumentProvider.createInstance(contentProvider);
            PdfCreate.download(documentProvider.getDocument(), filename);
        };
    }
])

.factory('KeypadForm', [
    'gettextCatalog',
    'User',
    function (gettextCatalog, User) {
        return {
            getDialog: function (keypad) {
                var resolve = {};
                if (keypad) {
                    resolve = {
                        keypad: function () {
                            return keypad;
                        }
                    }
                }
                return {
                    template: 'static/templates/openslides_voting/keypad-form.html',
                    controller: (keypad) ? 'KeypadUpdateCtrl' : 'KeypadCreateCtrl',
                    className: 'ngdialog-theme-default',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: (resolve) ? resolve : null
                }
            },
            getFormFields: function () {
                return [
                {
                    key: 'number',
                    type: 'input',
                    templateOptions: {
                        label: gettextCatalog.getString('Keypad number'),
                        type: 'number',
                        required: true
                    }
                },
                {
                    key: 'user_id',
                    type: 'select-single',
                    templateOptions: {
                        label: gettextCatalog.getString('Participant'),
                        options:  User.filter({where: {groups_id: 2}, orderBy: 'full_name'}),
                        ngOptions: 'option.id as option.full_name for option in to.options',
                        placeholder: '(' + gettextCatalog.getString('Anonymous') + ')'
                    }
                }
                ]
            }
        };
    }
])

.controller('KeypadListCtrl', [
    '$scope',
    '$http',
    '$timeout',
    'ngDialog',
    'KeypadForm',
    'Keypad',
    'User',
    'VoteCollector',
    function ($scope, $http, $timeout, ngDialog, KeypadForm, Keypad, User, VoteCollector) {
        //Keypad.bindAll({}, $scope, 'keypads');
        // User.bindAll({}, $scope, 'users');
        VoteCollector.bindOne(1, $scope, 'vc');
        $scope.alert = {};

        $scope.$watch(function () {
            return Keypad.lastModified() + User.lastModified();
        }, function () {
            _.forEach(Keypad.getAll(), function (keypad) {
                keypad.active = keypad.isActive();
                keypad.identified = keypad.isIdentified();
            });
            $scope.keypads = Keypad.getAll();
        });

        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 50,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Handle table column sorting.
        $scope.sortColumn = 'number';
        $scope.reverse = false;
        $scope.toggleSort = function ( column ) {
            if ( $scope.sortColumn === column ) {
                $scope.reverse = !$scope.reverse;
            }
            $scope.sortColumn = column;
        };

        // Define custom search filter string.
        $scope.getFilterString = function (keypad) {
            var user = '';
            if (keypad.user) {
                user = keypad.user.get_full_name();
            }
            return [
                keypad.number,
                user
            ].join(" ");
        };

        // Open new/edit dialog.
        $scope.openDialog = function (keypad) {
            ngDialog.open(KeypadForm.getDialog(keypad));
        };

        // Delete functions.
        $scope.isDeleteMode = false;
        $scope.checkAll = function () {
            angular.forEach($scope.keypads, function (keypad) {
                keypad.selected = $scope.selectedAll;
            });
        };
        $scope.uncheckAll = function () {
            if (!$scope.isDeleteMode) {
                $scope.selectedAll = false;
                angular.forEach($scope.keypads, function (keypad) {
                    keypad.selected = false;
                });
            }
        };
        $scope.deleteMultiple = function () {
            // Delete selected keypads.
            angular.forEach($scope.keypads, function (keypad) {
                if (keypad.selected)
                    Keypad.destroy(keypad.id);
            });
            $scope.isDeleteMode = false;
            $scope.uncheckAll();
        };
        $scope.delete = function (keypad) {
            // Delete single keypad.
            Keypad.destroy(keypad.id);
        };

        // Keypad system test.
        $scope.startSysTest = function () {
            $scope.device = null;

            angular.forEach($scope.keypads, function (keypad) {
                keypad.in_range = false;
                keypad.battery_level = -1;
            });

            $http.get('/votecollector/device/').then(
                function (success) {
                    if (success.data.error) {
                        $scope.device = success.data.error;
                    }
                    else {
                        $scope.device = success.data.device;
                        if (success.data.connected) {
                            $http.get('/votecollector/start_ping/').then(
                                function (success) {
                                    if (success.data.error) {
                                        $scope.device = success.data.error;
                                    }
                                    else {
                                        // Stop test after 1 min.
                                        $timeout(function () {
                                            if ($scope.vc.is_voting && $scope.vc.voting_mode == 'Test') {
                                                $scope.stopSysTest();
                                            }
                                        }, 60000);
                                    }
                                }
                            );
                        }
                     }
                },
                function (failure) {
                    $scope.device = $scope.vc.getErrorMessage(failure.status, failure.statusText);
                }
            );
        };

        $scope.stopSysTest = function () {
            $http.get('/votecollector/stop/');
        };
    }
])

.controller('KeypadCreateCtrl', [
    '$scope',
    'Keypad',
    'KeypadForm',
    function ($scope, Keypad, KeypadForm) {
        $scope.model = {};
        $scope.formFields = KeypadForm.getFormFields();

        // Save keypad.
        $scope.save = function (keypad) {
            // Create a new keypad.
            Keypad.create(keypad).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    var message = '';
                    // TODO: Replace e with localized field label.
                    for (var e in error.data) {
                        message += e + ': ' + error.data[e] + ' ';
                    }
                    $scope.alert = {type: 'danger', msg: message, show: true};
                }
            );
        };
    }
])

.controller('KeypadUpdateCtrl', [
    '$scope',
    'Keypad',
    'KeypadForm',
    'keypad',
    function ($scope, Keypad, KeypadForm, keypad) {
        // Use a deep copy of keypad object so list view is not updated while editing the form.
        $scope.model = angular.copy(keypad);
        $scope.formFields = KeypadForm.getFormFields();

        // Save keypad.
        $scope.save = function (keypad) {
            // Inject the changed keypad (copy) object back into DS store.
            Keypad.inject(keypad);
            // Save changed keypad object on server side.
            Keypad.save(keypad).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    // Save error: revert all changes by restoring original keypad object
                    // from server.
                    Keypad.refresh(keypad);
                    var message = '';
                    for (var e in error.data) {
                        message += e + ': ' + error.data[e] + ' ';
                    }
                    $scope.alert = {type: 'danger', msg: message, show: true};
                }
            );
        };
    }
])

.controller('KeypadImportCtrl', [
    '$scope',
    'gettext',
    'Keypad',
    'User',
    function ($scope, gettext, Keypad, User) {
        // Set up pagination.
        // http://stackoverflow.com/questions/34775157/angular-ui-bootstrap-pagination-ng-model-not-updating
        // http://stackoverflow.com/questions/33181191/scope-currentpage-not-updating-angular-ui-pagination
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 100,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Configure csv.
        $scope.csvConfig = {
            accept: '.csv, .txt',
            encodingOptions: ['UTF-8', 'ISO-8859-1'],
            parseConfig: {
                skipEmptyLines: true
            }
        };

        // Load csv file.
        var FIELDS = ['first_name', 'last_name', 'number', 'keypad'];
        $scope.users = [];
        $scope.onCsvChange = function (csv) {
            var users = User.getAll(),
                records = [];

            $scope.clear();

            // Read csv rows.
            _.forEach(csv.data, function (row) {
                if (row.length >= 4) {
                    var filledRow = _.zipObject(FIELDS, row);
                    records.push(filledRow);
                }
            });
            // Validate each record.
            _.forEach(records, function (record) {
                record.selected = true;
                if (record.first_name == '' && record.last_name == '') {
                    // User is anonymous.
                    record.user_id = null;
                }
                else {
                    // Find user.
                    record.fullname = [record.first_name, record.last_name, record.number].join(' ');
                    var user = _.find(users, function (item) {
                        item.fullname = [item.first_name, item.last_name, item.number].join(' ');
                        return item.fullname == record.fullname;
                    });
                    if (user != undefined) {
                        record.user_id = user.id;
                        record.fullname = user.get_full_name();
                    }
                    else {
                        record.user_id = -1;
                        record.importerror = true;
                        record.user_error = gettext('Error: Participant not found.');
                    }
                }
                // Validate keypad number.
                var num = parseInt(record.keypad);
                if (isNaN(num) || num <= 0) {
                    record.importerror = true;
                    record.keypad_error = gettext('Error: Keypad number must be a positive integer value.')
                }
                else {
                    record.keypad = num;
                    if (Keypad.filter({ 'number': record.keypad }).length > 0) {
                        record.importerror = true;
                        record.keypad_error = gettext('Error: Keypad number already exists.');
                    }
                }
                $scope.users.push(record);
            });
            $scope.calcStats();
        };

        $scope.calcStats = function () {
            $scope.keypadsWillNotBeImported = 0;
            $scope.keypadsWillBeImported = 0;

            $scope.users.forEach(function (item) {
                if (!item.importerror && item.selected) {
                    $scope.keypadsWillBeImported++;
                } else {
                    $scope.keypadsWillNotBeImported++;
                }
            });
        };

        // Import keypads.
        $scope.import = function () {
            $scope.csvImporting = true;
            angular.forEach($scope.users, function (user) {
                if (user.selected && !user.importerror) {
                    // Create keypad.
                    Keypad.create({'number': user.keypad, 'user_id': user.user_id}).then(
                        function(success) {
                            user.imported = true;
                        }
                    );
                }
            });
            $scope.csvImported = true;
        };

        // Clear csv import preview.
        $scope.clear = function () {
            $scope.users = [];
            $scope.csvImporting = false;
            $scope.csvImported = false;
        };
    }
])

.factory('AbsenteeVoteForm', [
    'gettextCatalog',
    'User',
    'Motion',
    function (gettextCatalog, User, Motion) {
        return {
            getDialog: function (absenteeVote) {
                var resolve = {};
                if (absenteeVote) {
                    resolve = {
                        absenteeVote: function () {
                            return absenteeVote;
                        }
                    }
                }
                return {
                    template: 'static/templates/openslides_voting/absentee-vote-form.html',
                    controller: (absenteeVote) ? 'AbsenteeVoteUpdateCtrl' : 'AbsenteeVoteCreateCtrl',
                    className: 'ngdialog-theme-default',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: (resolve) ? resolve : null
                }
            },
            getFormFields: function () {
                var voteOptions = [
                    {id: 'Y', name: 'Ja'}
                ];
                return [
                {
                    key: 'delegate_id',
                    type: 'select-single',
                    templateOptions: {
                        label: gettextCatalog.getString('Participant'),
                        options: User.filter({where: {groups_id: 2}, orderBy: 'full_name'}),
                        ngOptions: 'option.id as option.full_name for option in to.options',
                        required: true
                    }
                },
                {
                    key: 'motion_id',
                    type: 'select-single',
                    templateOptions: {
                        label: gettextCatalog.getString('Motion'),
                        options: Motion.filter({orderBy: 'identifier'}),
                        ngOptions: 'option.id as option.getTitle() for option in to.options',
                        required: true
                    }
                },
                {
                        // className: 'col-xs-4',
                        key: 'vote',
                        type: 'select-single',
                        templateOptions: {
                            label: gettextCatalog.getString('Voting intention'),
                            options: [
                                {id: 'Y', value: gettextCatalog.getString('Yes')},
                                {id: 'N', value: gettextCatalog.getString('No')},
                                {id: 'A', value: gettextCatalog.getString('Abstain')}
                            ],
                            ngOptions: 'option.id as option.value for option in to.options',
                            required: true
                        }
                }
                ]
            }
        };
    }
])

.controller('AbsenteeVoteListCtrl', [
    '$scope',
    'ngDialog',
    'AbsenteeVoteForm',
    'AbsenteeVote',
    function ($scope, ngDialog, AbsenteeVoteForm, AbsenteeVote) {
        AbsenteeVote.bindAll({}, $scope, 'absenteeVotes');
        $scope.alert = {};

        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 50,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Handle table column sorting.
        $scope.sortColumn = 'user.full_name';
        $scope.reverse = false;
        $scope.toggleSort = function (column) {
            if ( $scope.sortColumn === column ) {
                $scope.reverse = !$scope.reverse;
            }
            $scope.sortColumn = column;
        };

        // Define custom search filter string.
        $scope.getFilterString = function (absenteeVote) {
            return [
                absenteeVote.user.full_name,
                absenteeVote.getMotionTitle(),
                absenteeVote.getVote()
            ].join(' ');
        };

        // Open new/edit dialog.
        $scope.openDialog = function (absenteeVote) {
            ngDialog.open(AbsenteeVoteForm.getDialog(absenteeVote));
        };

        // Delete functions.
        $scope.isDeleteMode = false;
        $scope.checkAll = function () {
            angular.forEach($scope.absenteeVotes, function (absenteeVote) {
                absenteeVote.selected = $scope.selectedAll;
            });
        };
        $scope.uncheckAll = function () {
            if (!$scope.isDeleteMode) {
                $scope.selectedAll = false;
                angular.forEach($scope.absenteeVotes, function (absenteeVote) {
                    absenteeVote.selected = false;
                });
            }
        };
        $scope.deleteMultiple = function () {
            // Delete selected absentee votes.
            angular.forEach($scope.absenteeVotes, function (absenteeVote) {
                if (absenteeVote.selected)
                    AbsenteeVote.destroy(absenteeVote.id);
            });
            $scope.isDeleteMode = false;
            $scope.uncheckAll();
        };
        $scope.delete = function (absenteeVote) {
            // Delete single absentee vote.
            AbsenteeVote.destroy(absenteeVote.id);
        };
    }
])

.controller('AbsenteeVoteCreateCtrl', [
    '$scope',
    'AbsenteeVote',
    'AbsenteeVoteForm',
    function ($scope, AbsenteeVote, AbsenteeVoteForm) {
        $scope.model = {};
        $scope.formFields = AbsenteeVoteForm.getFormFields();

        // Save absentee vote.
        $scope.save = function (absenteeVote) {
            // Create an absentee vote.
            AbsenteeVote.create(absenteeVote).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    var message = '';
                    for (var e in error.data) {
                        message += e + ': ' + error.data[e] + ' ';
                    }
                    $scope.alert = {type: 'danger', msg: message, show: true};
                }
            );
        };

    }
])

.controller('AbsenteeVoteUpdateCtrl', [
    '$scope',
    'AbsenteeVote',
    'AbsenteeVoteForm',
    'absenteeVote',
    function ($scope, AbsenteeVote, AbsenteeVoteForm, absenteeVote) {
        // Use a deep copy of absentee vote object so list view is not updated while editing the form.
        $scope.model = angular.copy(absenteeVote);
        $scope.formFields = AbsenteeVoteForm.getFormFields();

        // Save absentee vote.
        $scope.save = function (absenteeVote) {
            // Inject the changed absentee vote (copy) object back into DS store.
            AbsenteeVote.inject(absenteeVote);
            // Save changed absentee vote object on server side.
            AbsenteeVote.save(absenteeVote).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    // Save error: revert all changes by restoring original absentee vote object
                    // from server.
                    AbsenteeVote.refresh(absenteeVote);
                    var message = '';
                    for (var e in error.data) {
                        message += e + ': ' + error.data[e] + ' ';
                    }
                    $scope.alert = {type: 'danger', msg: message, show: true};
                }
            );
        };
    }
])

.controller('AbsenteeVoteImportCtrl', [
    '$scope',
    'gettext',
    'AbsenteeVote',
    'User',
    'Motion',
    function ($scope, gettext, AbsenteeVote, User, Motion) {
        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 100,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Configure csv.
        $scope.csvConfig = {
            accept: '.csv, .txt',
            encodingOptions: ['UTF-8', 'ISO-8859-1'],
            parseConfig: {
                skipEmptyLines: true
            }
        };

        // Load csv file.
        var FIELDS = ['first_name', 'last_name', 'number', 'motion_identifier', 'vote'];
        $scope.users = [];
        $scope.delegateVotes = [];
        $scope.onCsvChange = function (csv) {
            var users = User.getAll(),
                motions = Motion.getAll(),
                records = [];

            $scope.clear();

            // Read csv rows.
            _.forEach(csv.data, function (row) {
                if (row.length >= 5) {
                    var filledRow = _.zipObject(FIELDS, row);
                    records.push(filledRow);
                }
            });
            // Validate each record.
            _.forEach(records, function (record) {
                record.selected = true;
                if (record.first_name == '' && record.last_name == '') {
                    // User is anonymous.
                    record.user_id = null;
                }
                else {
                    // Find user.
                    record.fullname = [record.first_name, record.last_name, record.number].join(' ');
                    var user = _.find(users, function (item) {
                        item.fullname = [item.first_name, item.last_name, item.number].join(' ');
                        return item.fullname == record.fullname;
                    });
                    if (user !== undefined) {
                        record.user_id = user.id;
                        record.fullname = user.get_full_name();
                    }
                    else {
                        record.user_id = -1;
                        record.importerror = true;
                        record.user_error = gettext('Error: Participant not found.');
                    }
                }
                // Find motion.
                var motions = Motion.filter({identifier: record.motion_identifier});
                if (motions.length == 1) {
                    record.motion_id = motions[0].id;
                    record.motion = motions[0].identifier + ' - ' + motions[0].getTitle();
                }
                else {
                    record.importerror = true;
                    record.motion_error = gettext('Error: Motion not found.');
                }
                // Validate vote.
                if (['Y', 'N', 'A'].indexOf(record.vote) == -1) {
                    record.importerror = true;
                    record.vote_error = gettext('Error: Vote must be one of Y, N, A.');
                }
                // Temporarily create absentee vote instance to look up vote properties.
                var av = AbsenteeVote.createInstance({vote: record.vote});
                record.vote_name = av.getVote();
                record.vote_icon = av.getVoteIcon();

                $scope.delegateVotes.push(record);
            });
            $scope.calcStats();
        };

        $scope.calcStats = function () {
            $scope.votesWillNotBeImported = 0;
            $scope.votesWillBeImported = 0;

            $scope.delegateVotes.forEach(function (item) {
                if (!item.importerror && item.selected) {
                    $scope.votesWillBeImported++;
                } else {
                    $scope.votesWillNotBeImported++;
                }
            });
        };

        // Import absentee votes.
        $scope.import = function () {
            $scope.csvImporting = true;
            angular.forEach($scope.delegateVotes, function (delegateVote) {
                if (delegateVote.selected && !delegateVote.importerror) {
                    // Look for an existing vote.
                    var avs = AbsenteeVote.filter({
                        delegate_id: delegateVote.user_id,
                        motion_id: delegateVote.motion_id
                    });
                    if (avs.length == 1) {
                        // Update vote.
                        avs[0].vote = delegateVote.vote;
                        AbsenteeVote.save(avs[0]).then(function (success) {
                            delegateVote.imported = true;
                        });
                    }
                    else {
                        // Create vote.
                        AbsenteeVote.create({
                            delegate_id: delegateVote.user_id,
                            motion_id: delegateVote.motion_id,
                            vote: delegateVote.vote
                        }).then(function (success) {
                            delegateVote.imported = true;
                        });
                    }
                }
            });
            $scope.csvImported = true;
        };

        // Clear csv import preview.
        $scope.clear = function () {
            $scope.delegateVotes = [];
            $scope.csvImporting = false;
            $scope.csvImported = false;
        };
    }
])

}());