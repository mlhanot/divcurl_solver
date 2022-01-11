from IPython.display import HTML, display

display(HTML('''<script>
    code_show = new WeakMap();
    function code_toggle(el) {
        cell = el.closest(".cell").getElementsByClassName("input")[0];
        if (!(code_show.has(cell))) {
            if(cell.style.display == "none") {
                code_show.set(cell,false);
            } else {
                code_show.set(cell,true);
            }
        }
        //console.log(el);
        //console.log(el.closest(".cell"));
        //console.log(el.closest(".cell").getElementsByClassName("input"));
        //console.log(code_show);
        if (code_show.get(cell)){
            cell.style.display = 'none';
        } else {
            cell.style.display = '';
        }
        code_show.set(cell,!code_show.get(cell));
    } 

    config = { attributes: false, childList: true, subtree: false };
    callback = function(mutationsList, observer) {
        if(observer.ref_cell.dataset.result_show == "false") {
            for(const mutation of mutationsList) {
                if ((mutation.type === 'childList') && (mutation.addedNodes.length > 0)) {
                  if(mutation.addedNodes[0].getElementsByTagName("form").length > 0) {
                      //console.log("base elem");
                    } else {
                      mutation.addedNodes[0].style.display = "none";
                    }
                }
            }
        }
    };

    result_show_observer = typeof result_show_observer == 'undefined'? new WeakMap() : result_show_observer;

    function result_toggle(el) {
        cell = el.closest(".cell"); // allow to store state between invocation

        if (!(result_show_observer.has(cell))) {
            console.log("Creating an observer to preserv state");
            result_show_observer.set(cell,"done");
            observer = new MutationObserver(callback);
            observer.ref_cell = cell;
            observer.observe(el.closest(".output"), config);
        }

        if (!(cell.dataset.result_show)) {
            cell.dataset.result_show = "true";
        }

        elparent = el.closest(".output_area");
        elsibling = el.closest(".output").getElementsByClassName("output_area");
        if (cell.dataset.result_show == "true"){
            for (const item of elsibling) {
              if (item != elparent) {
                item.style.display = 'none';
              }
            }
            cell.dataset.result_show = "false";
        } else {
            for (const item of elsibling) {
              if (item != elparent) {
                item.style.display = '';
              }
            }
            cell.dataset.result_show = "true";
        }
    }
    function nothing() {
    } 
    </script>
    '''))
    
def insertButtonCode():
    display(HTML('''<form  action="javascript:nothing()"><input onclick="code_toggle(this)" type="submit" value="Click here to toggle on/off the raw code."></form>'''))
    
def insertButtonResult():
    display(HTML('''<form action="javascript:nothing()"><input onclick="result_toggle(this)" type="submit" value="Click here to toggle on/off the resut."></form>'''))

