/* For fields repeated as list items */

function autoduplicate() {
  var new_li = $( this ).clone( true );
  $( new_li ).find( "label" ).attr( "for", function(index, value) {
    return value.replace(/-(\d+)(-\w+)?$/, function(str, p1, p2, offset, s) {
      if ( p2 ) {
      return '-' + (Number(p1) + 1) + p2;
      }
      return '-' + (Number(p1) + 1);
    });
  });
  $( new_li ).find( ":input" ).attr( "id", function(index, value) {
    return value.replace(/-(\d+)(-\w+)?$/, function(str, p1, p2, offset, s) {
      if ( p2 ) {
      return '-' + (Number(p1) + 1) + p2;
      }
      return '-' + (Number(p1) + 1);
    });
  });
  $( new_li ).find( ":input" ).attr( "name", function(index, value) {
    return value.replace(/-(\d+)(-\w+)?$/, function(str, p1, p2, offset, s) {
      if ( p2 ) {
      return '-' + (Number(p1) + 1) + p2;
      }
      return '-' + (Number(p1) + 1);
    });
  });
  $( new_li ).find( ":input" ).val(function() {return this.defaultValue});
  $( new_li ).one( "change", autoduplicate );
  $( this ).after( new_li );
}

$( ".form-list > li:last-child" )
  .one( "change", autoduplicate );

$( "input[list='keyword-list']" ).parent().filter(":last-child")
  .one( "change", autoduplicate );

/* Cleaning help text */

$( ".form-group" ).find( ".help-block" ).hide();

$( ":input" ).focus(function() {
  $( this ).closest( ".form-group" ).find( ".help-block" )
  .filter( ":hidden" ).show(400);
});

$( ".form-group" ).focusout(function (event) {
  if ( $( this ).has( event.relatedTarget ).length == 0 ) {
    $( this ).find( ".help-block" ).hide(400);
  }
});
