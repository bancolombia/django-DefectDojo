function sleep(ms) {
    const start = new Date().getTime();
    while (new Date().getTime() < start + ms) {
    }
    }

$(document).ready(function() {
    $(document).on("click", "#confirmed_action_modal", function() {
        $('#spinnerContainer').modal('show') 
        $.ajax({
            url: "/product/162/view_transfer_findings/all",
            type: "GET",
            success: function(response)
            {
            $('#spinnerContainer').modal('hide') 
            sleep(500);
            $('#confirmedModal').modal('hide');
            },
            error: function(error) {
                console.error(error);
                $('#spinnerContainer').modal('hide') 
            }
        });
        })
});
